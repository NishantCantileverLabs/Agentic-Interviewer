"""T7 — decision brief: recruiter layer + audit layer, deterministic assembly.

The hire signal is computed IN CODE from the weighted rubric vs role-config
thresholds — the LLM never decides it. Phase 1 assembles the recruiter layer
deterministically from the evaluation itself (top/bottom competencies with
their cited evidence), which makes the hard rule — every recruiter claim
traces to an audit citation — true by construction.
"""

import html
import io
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from minio import Minio
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.models import Brief, Evaluation, LLMCall, PromptVersion, RoleConfig, Session

DEFAULT_THRESHOLDS = {"strong_hire": 4.4, "hire": 3.6, "no_hire": 2.6}


def hire_signal(weighted_score: float, thresholds: dict[str, float]) -> str:
    if weighted_score >= thresholds.get("strong_hire", 4.4):
        return "strong hire"
    if weighted_score >= thresholds.get("hire", 3.6):
        return "hire"
    if weighted_score >= thresholds.get("no_hire", 2.6):
        return "no hire"
    return "strong no hire"


def build_summary(
    evaluation: dict[str, Any],
    signals: dict[str, Any],
    competencies: list[dict[str, Any]],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    """Recruiter + audit layers as JSON. Pure — unit-tested."""
    comp_scores = evaluation["competencies"]
    weights = {c["id"]: float(c["weight"]) for c in competencies}

    scored = {
        cid: c for cid, c in comp_scores.items() if c.get("score_1_to_5") is not None
    }
    total_weight = sum(weights.get(cid, 0) for cid in scored) or 1.0
    weighted = sum(
        scored[cid]["score_1_to_5"] * weights.get(cid, 0) for cid in scored
    ) / total_weight

    def top_evidence_quote(cid: str) -> dict[str, Any] | None:
        c = comp_scores.get(cid, {})
        refs = c.get("evidence_refs", [])
        for ev in c.get("evidence", []):
            if ev["event_id"] in refs:
                return {"event_id": ev["event_id"], "quote": ev["quote"]}
        return None

    ranked = sorted(scored, key=lambda cid: scored[cid]["score_1_to_5"], reverse=True)
    strengths = [
        {
            "competency": cid,
            "score": scored[cid]["score_1_to_5"],
            "statement": scored[cid]["rationale"],
            "citation": top_evidence_quote(cid),
        }
        for cid in ranked[:3]
        if scored[cid]["score_1_to_5"] >= 3
    ]
    risks = [
        {
            "competency": cid,
            "score": scored[cid]["score_1_to_5"],
            "statement": scored[cid]["rationale"],
            "citation": top_evidence_quote(cid),
        }
        for cid in reversed(ranked)
        if scored[cid]["score_1_to_5"] <= 3
    ][:3]

    unscored = [cid for cid in comp_scores if cid not in scored]
    uncertainty = []
    if unscored:
        uncertainty.append(
            f"No valid score could be produced for: {', '.join(unscored)} — "
            "flagged for human review."
        )
    low_conf = [cid for cid, c in scored.items() if c.get("confidence", 1) < 0.5]
    if low_conf:
        uncertainty.append(
            f"Low evidence confidence for: {', '.join(low_conf)}."
        )
    uncertainty.append(
        "Technical ability was assessed on a small number of problems in one "
        "session; breadth beyond them is not established."
    )

    integrity = []
    for p in signals.get("flagged_pastes", []):
        integrity.append(
            f"A paste of {p['length']} characters was recorded (event {p['event_id']}). "
            "Presented for reviewer attention; pastes can be legitimate."
        )
    if signals.get("tab_switches_away"):
        integrity.append(
            f"The candidate's tab lost focus {signals['tab_switches_away']} time(s). "
            "Presented for reviewer attention only."
        )

    return {
        "recruiter": {
            "signal": hire_signal(weighted, thresholds),
            "weighted_score": round(weighted, 2),
            "strengths": strengths,
            "risks": risks,
            "uncertainty": uncertainty,
        },
        "audit": {
            "rubric": comp_scores,
            "signals": signals,
            "thresholds": thresholds,
            "degraded": evaluation.get("degraded", False),
            "integrity_notes": integrity,
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def render_html(summary: dict[str, Any], meta: dict[str, Any]) -> str:
    """Self-contained offline HTML (no external assets)."""
    r = summary["recruiter"]
    a = summary["audit"]
    e = html.escape

    def items(entries: list[dict[str, Any]]) -> str:
        out = []
        for s in entries:
            cite = s.get("citation") or {}
            quote = (
                f"<blockquote>&ldquo;{e(cite.get('quote', ''))}&rdquo; "
                f"<a href='#ev-{cite.get('event_id')}'>[event {cite.get('event_id')}]</a>"
                f"</blockquote>"
                if cite
                else ""
            )
            out.append(
                f"<li><strong>{e(s['competency'])}</strong> (score {s['score']}/5): "
                f"{e(s['statement'])}{quote}</li>"
            )
        return "".join(out) or "<li>None identified.</li>"

    rubric_rows = []
    for cid, c in a["rubric"].items():
        evidence_html = "".join(
            f"<div class='ev' id='ev-{ev['event_id']}'>[{ev['event_id']}] "
            f"&ldquo;{e(ev['quote'])}&rdquo; <em>{e(ev['why_relevant'])}</em></div>"
            for ev in c.get("evidence", [])
        )
        rubric_rows.append(
            f"<tr><td>{e(cid)}</td><td>{c.get('score_1_to_5', '—')}</td>"
            f"<td>{c.get('confidence', '—')}</td>"
            f"<td>{e(c.get('rationale', 'no valid score — flagged for review'))}"
            f"{evidence_html}</td></tr>"
        )

    integrity = "".join(f"<li>{e(n)}</li>" for n in a["integrity_notes"]) or "<li>None recorded.</li>"
    uncertainty = "".join(f"<li>{e(u)}</li>" for u in r["uncertainty"])
    signals_json = e(json.dumps(a["signals"], indent=1))
    signal_class = r["signal"].replace(" ", "-")

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Interview Brief — {e(meta.get('candidate_label', ''))}</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1a232e;line-height:1.5}}
h1,h2{{color:#0b2545}} .signal{{display:inline-block;padding:.4rem 1.2rem;border-radius:999px;font-weight:700;font-size:1.1rem}}
.signal.strong-hire{{background:#d3f9d8;color:#0b6623}} .signal.hire{{background:#e7f5ff;color:#1864ab}}
.signal.no-hire{{background:#fff3bf;color:#8a6d00}} .signal.strong-no-hire{{background:#ffe3e3;color:#a61e1e}}
table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #d5dce4;padding:.5rem;text-align:left;vertical-align:top}}
blockquote{{margin:.3rem 0;color:#495866;border-left:3px solid #b7c3cf;padding-left:.6rem;font-size:.92rem}}
.ev{{margin:.35rem 0;font-size:.85rem;color:#495866}} pre{{background:#f1f4f7;padding:.8rem;border-radius:8px;overflow-x:auto;font-size:.8rem}}
.meta{{color:#68788c;font-size:.85rem}} .audit{{margin-top:3rem;border-top:2px solid #d5dce4;padding-top:1rem}}
</style></head><body>
<h1>Interview Decision Brief</h1>
<p class="meta">Candidate: {e(meta.get('candidate_label', ''))} · Session {e(meta.get('session_id', ''))}
 · Generated {e(summary['generated_at'])} · Evaluation v{meta.get('evaluation_version', '?')}</p>
<p><span class="signal {signal_class}">{e(r['signal'].upper())}</span>
 &nbsp;weighted score {r['weighted_score']}/5</p>
{'<p><strong>⚠ This evaluation is flagged degraded — scores need human review.</strong></p>' if a['degraded'] else ''}
<h2>Strengths</h2><ul>{items(r['strengths'])}</ul>
<h2>Risks</h2><ul>{items(r['risks'])}</ul>
<h2>What this assessment does not establish</h2><ul>{uncertainty}</ul>
<div class="audit">
<h1>Audit layer</h1>
<p class="meta">Evaluation model: {e(meta.get('model', ''))} · Scoring prompt: {e(meta.get('prompt_version', ''))}
 · Conduct prompts: versioned per round in llm_calls</p>
<h2>Full rubric with evidence</h2>
<table><tr><th>Competency</th><th>Score</th><th>Confidence</th><th>Rationale &amp; evidence</th></tr>
{''.join(rubric_rows)}</table>
<h2>For reviewer attention</h2><ul>{integrity}</ul>
<h2>Deterministic process signals</h2><pre>{signals_json}</pre>
</div></body></html>"""


def generate_brief(db: DbSession, evaluation_id: uuid.UUID) -> uuid.UUID:
    evaluation = db.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise RuntimeError(f"evaluation {evaluation_id} not found")
    session = db.get(Session, evaluation.session_id)
    if session is None:
        raise RuntimeError(f"session {evaluation.session_id} not found")
    role_config = db.get(RoleConfig, session.role_config_id) if session.role_config_id else None
    thresholds = dict(DEFAULT_THRESHOLDS)
    competencies: list[dict[str, Any]] = []
    if role_config:
        thresholds.update(role_config.thresholds or {})
        competencies = [
            {"id": cid, "weight": w} for cid, w in (role_config.weights or {}).items()
        ]
    if not competencies:
        # fall back to the plan's competency weights
        from app.models import InterviewPlan

        plan = db.get(InterviewPlan, session.plan_id) if session.plan_id else None
        competencies = (plan.plan.get("competencies") if plan else None) or []

    summary = build_summary(evaluation.rubric, evaluation.signals, competencies, thresholds)

    pv = db.get(PromptVersion, evaluation.prompt_version_id)
    html_doc = render_html(
        summary,
        {
            "candidate_label": session.candidate_label,
            "session_id": str(session.id),
            "evaluation_version": evaluation.version,
            "model": evaluation.model,
            "prompt_version": pv.name if pv else "?",
        },
    )

    settings = get_settings()
    client = Minio(
        settings.s3_endpoint.replace("http://", "").replace("https://", ""),
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        secure=settings.s3_endpoint.startswith("https"),
    )
    key = f"{session.id}/brief-v{evaluation.version}.html"
    data = html_doc.encode("utf-8")
    client.put_object("briefs", key, io.BytesIO(data), len(data), content_type="text/html")

    brief = Brief(
        id=uuid.uuid4(),
        org_id=session.org_id,
        session_id=session.id,
        evaluation_id=evaluation.id,
        html_object_key=key,
        summary=summary,
    )
    db.add(brief)
    db.commit()
    return brief.id


def llm_call_count(db: DbSession, session_id: uuid.UUID) -> int:
    from sqlalchemy import func as _func

    # COUNT in the DB — loading every id row to call len() scaled with the
    # interview's LLM-call volume
    return int(
        db.scalar(
            select(_func.count(LLMCall.id)).where(LLMCall.session_id == session_id)
        )
        or 0
    )
