"""T27 — cross-round aggregation: weighted roll-up in code, merged evidence,
citation-validated consistency, trajectory + confidence scaling.

Roll-up math is pure and unit-tested. The consistency pass is the only LLM
involvement and every claim it makes must cite events in BOTH sessions —
uncited claims are dropped (invariant #17), never shipped.
"""

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.eval.brief import DEFAULT_THRESHOLDS, hire_signal
from app.models import Evaluation, InterviewEvent, Session

log = logging.getLogger("aggregate")


def rollup_competencies(
    round_results: list[dict[str, Any]], round_weights: list[float]
) -> dict[str, Any]:
    """round_results: [{round_index, round_type, rubric}, ...] in order.
    Same competency across rounds -> weighted merge, all evidence kept with
    round attribution. Pure — unit-tested against hand computation."""
    merged: dict[str, dict[str, Any]] = {}
    for result, weight in zip(round_results, round_weights, strict=True):
        comps = (result.get("rubric") or {}).get("competencies", {})
        for cid, entry in comps.items():
            score = entry.get("score_1_to_5")
            if not isinstance(score, int):
                continue
            slot = merged.setdefault(
                cid, {"weighted_sum": 0.0, "weight_sum": 0.0, "observations": 0,
                      "evidence": [], "per_round": []}
            )
            slot["weighted_sum"] += score * weight
            slot["weight_sum"] += weight
            slot["observations"] += 1
            slot["per_round"].append(
                {"round_index": result["round_index"], "round_type": result["round_type"],
                 "score": score, "confidence": entry.get("confidence")}
            )
            for ev_item in entry.get("evidence", []):
                slot["evidence"].append({**ev_item, "round_index": result["round_index"]})

    out = {}
    for cid, slot in merged.items():
        score = slot["weighted_sum"] / slot["weight_sum"] if slot["weight_sum"] else None
        out[cid] = {
            "score": round(score, 2) if score is not None else None,
            "observations": slot["observations"],
            "confidence_band": (
                "high" if slot["observations"] >= 3
                else "medium" if slot["observations"] == 2 else "low"
            ),
            "per_round": slot["per_round"],
            "evidence": slot["evidence"][:12],
        }
    return out


def trajectory(round_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Mean rubric score per round in sequence; improving/steady/declining."""
    means = []
    for r in round_results:
        comps = (r.get("rubric") or {}).get("competencies", {})
        scores = [e["score_1_to_5"] for e in comps.values()
                  if isinstance(e.get("score_1_to_5"), int)]
        means.append(round(sum(scores) / len(scores), 2) if scores else None)
    valid = [m for m in means if m is not None]
    if len(valid) < 2:
        label = "single_round"
    elif valid[-1] - valid[0] > 0.4:
        label = "improving"
    elif valid[0] - valid[-1] > 0.4:
        label = "declining"
    else:
        label = "steady"
    return {"per_round_mean": means, "label": label,
            "fatigue_note": ("Later rounds in the same sitting can reflect fatigue; "
                             "interpret decline cautiously." if label == "declining" else None)}


def validate_consistency_claims(
    claims: list[dict[str, Any]], valid_ids_by_session: dict[str, set[int]]
) -> list[dict[str, Any]]:
    """Invariant #17: every claim must cite >=1 resolvable event id in EVERY
    session it references. Non-conforming claims are dropped."""
    out = []
    for claim in claims:
        cites = claim.get("citations") or {}
        if len(cites) < 2:
            continue
        ok = all(
            sid in valid_ids_by_session
            and any(int(e) in valid_ids_by_session[sid] for e in (ids or []))
            for sid, ids in cites.items()
        )
        if ok:
            out.append(claim)
    return out


async def consistency_pass(
    db: DbSession, sessions: list[Session]
) -> list[dict[str, Any]]:
    """Two-pass style LLM comparison across rounds, then hard validation."""
    if len(sessions) < 2:
        return []
    from app.config import get_settings
    from app.eval.pipeline import (
        _log_llm_call,
        _parse_json_object,
        _prompt_version,
        build_transcript,
    )
    from providers import ContextBlock, LLMRequest, get_provider

    valid_ids: dict[str, set[int]] = {}
    excerpts = []
    for s in sessions:
        rows = list(
            db.scalars(
                select(InterviewEvent)
                .where(InterviewEvent.session_id == s.id)
                .order_by(InterviewEvent.seq)
            )
        )
        valid_ids[str(s.id)] = {r.id for r in rows}
        events = [{"id": r.id, "ts": r.ts, "type": r.type, "payload": r.payload} for r in rows]
        excerpts.append(
            f"SESSION {s.id} (round_type={s.round_type or 'unknown'}):\n"
            + build_transcript(events)[:6000]
        )

    # invariant #2: the prompt lives in /prompts (versioned) and the call is
    # logged to llm_calls — it was previously inlined and unlogged
    try:
        pv = _prompt_version(db, "evaluate/consistency_v1")
        provider = get_provider()
        result = await provider.complete(
            LLMRequest(
                model=get_settings().eval_model,
                system_blocks=[ContextBlock(pv.content, cached=True)],
                messages=[{"role": "user", "content": "\n\n".join(excerpts)}],
                max_tokens=1500,
            )
        )
        _log_llm_call(db, sessions[0].id, sessions[0].org_id, pv, result)
        claims = _parse_json_object(result.text).get("claims", [])
    except Exception as exc:  # noqa: BLE001 - aggregation must not fail the pipeline
        log.warning("consistency pass failed: %s", exc)
        return []
    return validate_consistency_claims(claims, valid_ids)


async def build_aggregate(
    db: DbSession, candidacy_id: uuid.UUID, pipeline_rounds: list[dict[str, Any]],
    round_sessions: dict[str, str], thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    sessions: list[Session] = []
    round_results = []
    weights = []
    for idx_str, sid in sorted(round_sessions.items(), key=lambda kv: int(kv[0])):
        idx = int(idx_str)
        session = db.get(Session, uuid.UUID(sid))
        if session is None:
            continue
        ev = db.scalar(
            select(Evaluation).where(Evaluation.session_id == session.id)
            .order_by(Evaluation.version.desc()).limit(1)
        )
        if ev is None:
            continue
        sessions.append(session)
        rdef = pipeline_rounds[idx] if idx < len(pipeline_rounds) else {}
        round_results.append(
            {"round_index": idx, "round_type": session.round_type or rdef.get("round_type"),
             "rubric": ev.rubric, "session_id": str(session.id)}
        )
        weights.append(float(rdef.get("weight", 1.0)))

    merged = rollup_competencies(round_results, weights)
    scores = [c["score"] for c in merged.values() if c["score"] is not None]
    overall = round(sum(scores) / len(scores), 2) if scores else None
    thr = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    return {
        "competencies": merged,
        "overall_score": overall,
        "signal": hire_signal(overall, thr) if overall is not None else "insufficient data",
        "trajectory": trajectory(round_results),
        "rounds_evaluated": len(round_results),
        "consistency": await consistency_pass(db, sessions),
        "uncertainty": [
            f"{cid}: observed in {c['observations']} round(s) — {c['confidence_band']} confidence"
            for cid, c in merged.items()
        ],
    }


def render_aggregate_html(candidacy_name: str, agg: dict[str, Any]) -> str:
    import html as h

    rows = "".join(
        f"<tr><td>{h.escape(cid)}</td><td>{c['score']}</td><td>{c['observations']}</td>"
        f"<td>{c['confidence_band']}</td></tr>"
        for cid, c in agg["competencies"].items()
    )
    cons = "".join(
        f"<li>[{h.escape(c.get('kind', ''))}] {h.escape(c.get('statement', ''))}</li>"
        for c in agg.get("consistency", [])
    ) or "<li>No cross-round claims met the citation bar.</li>"
    unc = "".join(f"<li>{h.escape(u)}</li>" for u in agg.get("uncertainty", []))
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Pipeline Brief</title>
<style>body{{font-family:system-ui;max-width:860px;margin:2rem auto;padding:0 1rem;color:#1a232e}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #d5dce4;padding:.5rem}}</style>
</head><body><h1>Cross-round Brief — {h.escape(candidacy_name)}</h1>
<p><b>{h.escape(str(agg["signal"]).upper())}</b> · overall {agg["overall_score"]}/5 ·
trajectory: {h.escape(agg["trajectory"]["label"])}</p>
<h2>Competency roll-up</h2>
<table><tr><th>Competency</th><th>Score</th><th>Rounds observed</th><th>Confidence</th></tr>{rows}</table>
<h2>Cross-round consistency (citation-validated)</h2><ul>{cons}</ul>
<h2>Confidence statements</h2><ul>{unc}</ul></body></html>"""
