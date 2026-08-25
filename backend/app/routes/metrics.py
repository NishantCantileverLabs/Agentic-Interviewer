"""T9 — latency dashboard data + LLM call inspectability.
T8 — human evaluations, session listing, calibration report."""

import statistics
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy import text as _text
from sqlalchemy.orm import Session as DbSession

from app.eval.calibration import calibration_report
from app.models import (
    Brief,
    Evaluation,
    HumanEvaluation,
    InterviewEvent,
    LLMCall,
    RoleConfig,
    Session,
)
from app.tenancy import OrgContext, get_db, require_role


def SessionLocal_health():  # noqa: N802 - tiny local alias
    from app.db import SessionLocal, set_rls_context

    db = SessionLocal()
    # cross-org operator counter (counts only, no tenant data leaves)
    set_rls_context(db, bypass=True)
    return db

router = APIRouter()


def _pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, round(p * (len(ordered) - 1)))
    return ordered[int(idx)]


@router.get("/metrics/eval-health")
def eval_health(
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> dict[str, Any]:
    """Operator visibility for the eval pipeline (audit finding: a wedged
    worker was invisible). Queue depth, dead-letter count, and sessions
    completed >10min ago with no evaluation ("stuck")."""
    import redis as _redis

    from app.config import get_settings

    settings = get_settings()
    depth = dead = -1
    try:
        r = _redis.Redis.from_url(settings.redis_url, socket_timeout=3)
        depth = int(r.llen(settings.eval_queue))
        dead = int(r.llen(f"{settings.eval_queue}:dead"))
    except _redis.RedisError:
        pass  # -1 signals "redis unreachable" to the dashboard
    db = SessionLocal_health()
    try:
        stuck = db.execute(
            _text(
                """
                SELECT count(*) FROM sessions s
                WHERE s.status = 'completed'
                  AND s.ended_at < now() - interval '10 minutes'
                  AND NOT EXISTS (
                    SELECT 1 FROM evaluations e WHERE e.session_id = s.id
                  )
                """
            )
        ).scalar()
    finally:
        db.close()
    return {
        "queue_depth": depth,
        "dead_letter": dead,
        "stuck_sessions": int(stuck or 0),
        "healthy": depth == 0 and dead == 0 and int(stuck or 0) == 0,
    }


@router.get("/metrics/latency")
def latency_metrics(
    limit: int = 20,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> dict[str, Any]:
    """Per-session voice latency stats from turn_latency events (T1 §2.3)."""
    limit = max(1, min(limit, 100))  # unbounded ?limit= was a DoS lever
    recent_sessions = list(
        db.scalars(select(Session).order_by(Session.created_at.desc()).limit(limit))
    )
    # ONE query for all sessions' turn_latency events (was one per session)
    sids = [s.id for s in recent_sessions]
    by_session: dict[uuid.UUID, list[dict[str, Any]]] = {sid: [] for sid in sids}
    if sids:
        for row in db.scalars(
            select(InterviewEvent)
            .where(
                InterviewEvent.session_id.in_(sids),
                InterviewEvent.type == "turn_latency",
            )
            .order_by(InterviewEvent.seq)
        ):
            by_session[row.session_id].append(row.payload)
    out = []
    for s in recent_sessions:
        turns = [
            p for p in by_session.get(s.id, [])
            if "e2e_first_audio_s" in p and not p.get("summary")
        ]
        if not turns:
            continue
        e2e = [float(t["e2e_first_audio_s"]) for t in turns]

        def stage(key: str, turns: list[dict[str, Any]] = turns) -> float | None:
            vals = [float(t[key]) for t in turns if key in t]
            return round(statistics.median(vals) * 1000) if vals else None

        out.append(
            {
                "session_id": str(s.id),
                "candidate_label": s.candidate_label,
                "created_at": s.created_at.isoformat(),
                "turns": len(e2e),
                "p50_ms": round(statistics.median(e2e) * 1000),
                "p95_ms": round(_pct(e2e, 0.95) * 1000),
                "stage_p50_ms": {
                    "eou": stage("eou_delay_s"),
                    "llm_ttft": stage("llm_ttft_s"),
                    "tts_ttfb": stage("tts_ttfb_s"),
                },
                "recent_e2e_ms": [round(v * 1000) for v in e2e[-30:]],
            }
        )
    return {"targets": {"p50_ms": 800, "p95_ms": 1500}, "sessions": out}


@router.get("/metrics/llm-calls")
def llm_call_metrics(
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            LLMCall.role,
            LLMCall.model,
            func.count(LLMCall.id),
            func.sum(LLMCall.input_tokens),
            func.sum(LLMCall.output_tokens),
            func.avg(LLMCall.ttft_ms),
            func.sum(LLMCall.cost_estimate),
        ).group_by(LLMCall.role, LLMCall.model)
    )
    return [
        {
            "role": role,
            "model": model,
            "calls": count,
            "input_tokens": int(in_tok or 0),
            "output_tokens": int(out_tok or 0),
            "avg_ttft_ms": round(float(ttft)) if ttft else None,
            "cost_estimate_usd": round(float(cost), 4) if cost else None,
        }
        for role, model, count, in_tok, out_tok, ttft, cost in rows
    ]


# ── T8: sessions list, human evaluations, calibration ────────────────


@router.get("/sessions")
def list_sessions(
    limit: int = 50,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 200))  # unbounded ?limit= was a DoS lever
    sessions = list(
        db.scalars(select(Session).order_by(Session.created_at.desc()).limit(limit))
    )
    sids = [s.id for s in sessions]
    # three grouped COUNTs instead of three queries PER session
    def _counts(model) -> dict:  # noqa: ANN001
        if not sids:
            return {}
        return {
            row[0]: row[1]
            for row in db.execute(
                select(model.session_id, func.count(model.id))
                .where(model.session_id.in_(sids))
                .group_by(model.session_id)
            ).all()
        }

    eval_counts = _counts(Evaluation)
    human_counts = _counts(HumanEvaluation)
    brief_counts = _counts(Brief)
    out = []
    for s in sessions:
        has_eval = eval_counts.get(s.id, 0)
        has_human = human_counts.get(s.id, 0)
        has_brief = brief_counts.get(s.id, 0)
        out.append(
            {
                "id": str(s.id),
                "candidate_label": s.candidate_label,
                "status": s.status,
                "created_at": s.created_at.isoformat(),
                "ai_evaluations": has_eval,
                "human_evaluations": has_human,
                "briefs": has_brief,
            }
        )
    return out


class HumanEvalIn(BaseModel):
    reviewer: str
    rubric: dict[str, Any]  # {competency: {"score_1_to_5": int, "notes": str}}


@router.post("/sessions/{session_id}/human-evaluation", status_code=201)
def submit_human_evaluation(
    session_id: uuid.UUID,
    body: HumanEvalIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> dict[str, str]:
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    for comp, entry in body.rubric.items():
        score = entry.get("score_1_to_5")
        if not isinstance(score, int) or not 1 <= score <= 5:
            raise HTTPException(422, f"invalid score for {comp}")
    row = HumanEvaluation(
        id=uuid.uuid4(),
        org_id=session.org_id,
        session_id=session_id,
        reviewer=body.reviewer,
        rubric=body.rubric,
    )
    db.add(row)
    db.commit()
    return {"id": str(row.id)}


def _score_map(rubric: dict[str, Any]) -> dict[str, int]:
    comps = rubric.get("competencies", rubric)
    return {
        c: entry["score_1_to_5"]
        for c, entry in comps.items()
        if isinstance(entry, dict) and isinstance(entry.get("score_1_to_5"), int)
    }


def _build_calibration(db: DbSession) -> dict[str, Any]:
    pairs = []
    session_ids = db.scalars(select(HumanEvaluation.session_id).distinct())
    for sid in session_ids:
        ai = db.scalar(
            select(Evaluation)
            .where(Evaluation.session_id == sid)
            .order_by(Evaluation.version.desc())
            .limit(1)
        )
        human = db.scalar(
            select(HumanEvaluation)
            .where(HumanEvaluation.session_id == sid)
            .order_by(HumanEvaluation.created_at.desc())
            .limit(1)
        )
        if ai is None or human is None:
            continue
        ai_scores, human_scores = _score_map(ai.rubric), _score_map(human.rubric)
        if ai_scores and human_scores:
            pairs.append({"session_id": str(sid), "ai": ai_scores, "human": human_scores})

    rc = db.scalars(select(RoleConfig).limit(1)).first()
    weights = dict(rc.weights) if rc and rc.weights else None
    threshold = float((rc.thresholds or {}).get("hire", 3.6)) if rc else 3.6
    return calibration_report(pairs, hire_threshold=threshold, weights=weights)


@router.get("/calibration")
def calibration(
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> dict[str, Any]:
    return _build_calibration(db)


@router.get("/calibration.html", response_class=HTMLResponse)
def calibration_html(
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> HTMLResponse:
    import html as h
    import json

    report = _build_calibration(db)
    warning = (
        "<div style='background:#ffe3e3;color:#a61e1e;padding:1rem;border-radius:8px;"
        "font-weight:700;font-size:1.1rem'>INSUFFICIENT DATA FOR RELIABLE CALIBRATION "
        f"— {report['n_sessions']} dual-scored session(s); "
        f"{report['min_sessions_for_calibration']} required. Do not quote correlations "
        "from this report.</div>"
        if report["insufficient_data"]
        else ""
    )
    comp_rows = "".join(
        f"<tr><td>{h.escape(c)}</td><td>{v['n']}</td><td>{v['spearman']}</td>"
        f"<td>{v['mean_abs_diff']}</td></tr>"
        for c, v in report["per_competency"].items()
    )
    dis_rows = "".join(
        f"<tr><td>{h.escape(d['session_id'])}</td><td>{h.escape(d['competency'])}</td>"
        f"<td>{d['ai']}</td><td>{d['human']}</td><td>{d['delta']}</td></tr>"
        for d in report["disagreements"]
    ) or "<tr><td colspan=5>None</td></tr>"
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>Calibration Report</title>
<style>body{{font-family:system-ui;max-width:860px;margin:2rem auto;padding:0 1rem;color:#1a232e}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}}td,th{{border:1px solid #d5dce4;padding:.5rem;text-align:left}}
pre{{background:#f1f4f7;padding:.8rem;border-radius:8px;font-size:.8rem}}</style></head><body>
<h1>AI vs Human Calibration</h1>{warning}
<p>Dual-scored sessions: {report["n_sessions"]} · Pass/fail agreement:
{report["pass_fail_agreement_rate"]} (hire threshold {report["hire_threshold"]})</p>
<h2>Per-competency</h2>
<table><tr><th>Competency</th><th>n</th><th>Spearman ρ</th><th>Mean |Δ|</th></tr>{comp_rows}</table>
<h2>Disagreements (|Δ| ≥ 2) — flagged for second human review</h2>
<table><tr><th>Session</th><th>Competency</th><th>AI</th><th>Human</th><th>Δ</th></tr>{dis_rows}</table>
<h2>Raw</h2><pre>{h.escape(json.dumps(report, indent=1))}</pre>
</body></html>"""
    return HTMLResponse(doc)
