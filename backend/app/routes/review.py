"""T15 — review queue (degraded + borderline inflows; integrity inflow lands
with proctoring when built), confirm/override with mandatory rationale
(invariant #10/#14), flag dispositions, same-role comparison."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session as DbSession

from app.eval.brief import DEFAULT_THRESHOLDS, hire_signal
from app.models import Brief, Evaluation, RoleConfig, Session
from app.models_phase23 import FlagDisposition, ReviewDecision
from app.tenancy import OrgContext, get_db, require_role

router = APIRouter()

BORDERLINE_BAND = 0.3  # hire signals within ±band of the hire threshold


def _weighted(rubric: dict[str, Any], weights: dict[str, float]) -> float | None:
    comps = rubric.get("competencies", {})
    scored = {c: e for c, e in comps.items() if isinstance(e.get("score_1_to_5"), int)}
    if not scored:
        return None
    total = sum(weights.get(c, 1.0) for c in scored) or 1.0
    return float(
        sum(e["score_1_to_5"] * weights.get(c, 1.0) for c, e in scored.items()) / total
    )


@router.get("/review-queue")
def review_queue(
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> list[dict[str, Any]]:
    rc = db.scalars(select(RoleConfig).limit(1)).first()
    weights = dict(rc.weights) if rc and rc.weights else {}
    thresholds = {**DEFAULT_THRESHOLDS, **((rc.thresholds or {}) if rc else {})}
    hire_thr = float(thresholds.get("hire", 3.6))

    evals = list(
        db.scalars(select(Evaluation).order_by(Evaluation.created_at.desc()).limit(200))
    )
    ev_sids = {e.session_id for e in evals}
    # scoped to the candidate evaluations (review_decisions is append-only and
    # grows forever — loading every id was unbounded), and sessions batched
    decided = (
        set(
            db.scalars(
                select(ReviewDecision.session_id).where(
                    ReviewDecision.session_id.in_(ev_sids)
                )
            )
        )
        if ev_sids
        else set()
    )
    sessions_by_id = (
        {x.id: x for x in db.scalars(select(Session).where(Session.id.in_(ev_sids)))}
        if ev_sids
        else {}
    )
    queue: list[dict[str, Any]] = []
    for ev in evals:
        if ev.session_id in decided:
            continue
        session = sessions_by_id.get(ev.session_id)
        if session is None:
            continue
        entry = {
            "session_id": str(ev.session_id),
            "candidate_label": session.candidate_label,
            "evaluation_version": ev.version,
            "created_at": ev.created_at.isoformat(),
        }
        if ev.rubric.get("degraded"):
            queue.append({**entry, "inflow": "degraded",
                          "reason": "evaluation has uncited/invalid scores"})
            continue
        weighted = _weighted(ev.rubric, weights)
        if weighted is not None and abs(weighted - hire_thr) <= BORDERLINE_BAND:
            queue.append({
                **entry, "inflow": "borderline",
                "reason": f"weighted {round(weighted, 2)} within ±{BORDERLINE_BAND} of "
                          f"hire threshold {hire_thr}",
                "signal": hire_signal(weighted, thresholds),
            })
    return queue


class DecisionIn(BaseModel):
    inflow: str  # integrity | degraded | borderline
    decision: str  # confirm | override
    rationale: str = ""


@router.post("/sessions/{session_id}/review-decision", status_code=201)
def submit_decision(
    session_id: uuid.UUID,
    body: DecisionIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> dict[str, str]:
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    if body.inflow not in ("integrity", "degraded", "borderline"):
        raise HTTPException(422, "invalid inflow")
    if body.decision not in ("confirm", "override"):
        raise HTTPException(422, "invalid decision")
    if body.decision == "override" and len(body.rationale.strip()) < 20:
        # Invariant #10: overrides carry mandatory written rationale
        # (≥20 chars per the workflow spec — "n/a" is not a rationale)
        raise HTTPException(422, "override requires a written rationale (at least 20 characters)")
    # Idempotency without violating append-only: a double-click (same
    # reviewer, same decision, same rationale) returns the existing row
    # instead of appending a duplicate. Different content still appends.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
        {"k": f"decision:{session_id}"},
    )
    dup = db.scalar(
        select(ReviewDecision)
        .where(
            ReviewDecision.session_id == session_id,
            ReviewDecision.reviewer_email == ctx.user_email,
            ReviewDecision.decision == body.decision,
            ReviewDecision.rationale == (body.rationale.strip() or "confirmed"),
        )
        .order_by(ReviewDecision.ts.desc())
        .limit(1)
    )
    if dup is not None:
        return {"id": str(dup.id)}
    row = ReviewDecision(
        org_id=session.org_id,
        session_id=session_id,
        reviewer_email=ctx.user_email,
        inflow=body.inflow,
        decision=body.decision,
        rationale=body.rationale.strip() or "confirmed",
    )
    db.add(row)
    db.commit()
    return {"id": str(row.id)}


class DispositionIn(BaseModel):
    signal: str
    disposition: str  # substantiated | benign | unclear


@router.post("/sessions/{session_id}/flag-disposition", status_code=201)
def submit_disposition(
    session_id: uuid.UUID,
    body: DispositionIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> dict[str, str]:
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    if body.disposition not in ("substantiated", "benign", "unclear"):
        raise HTTPException(422, "invalid disposition")
    row = FlagDisposition(
        org_id=session.org_id,
        session_id=session_id,
        signal=body.signal,
        disposition=body.disposition,
        reviewer_email=ctx.user_email,
    )
    db.add(row)
    db.commit()
    return {"id": str(row.id)}


@router.get("/compare")
def compare_candidates(
    session_a: uuid.UUID,
    session_b: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> dict[str, Any]:
    """Same-role comparison only — cross-role comparison is refused, not fudged."""
    out = {}
    role_ids = set()
    for key, sid in (("a", session_a), ("b", session_b)):
        session = db.get(Session, sid)
        if session is None:
            raise HTTPException(404, f"session {sid} not found")
        role_ids.add(str(session.role_config_id or session.plan_id))
        ev = db.scalar(
            select(Evaluation).where(Evaluation.session_id == sid)
            .order_by(Evaluation.version.desc()).limit(1)
        )
        brief = db.scalar(
            select(Brief).where(Brief.session_id == sid)
            .order_by(Brief.created_at.desc()).limit(1)
        )
        out[key] = {
            "session_id": str(sid),
            "candidate_label": session.candidate_label,
            "rubric": ev.rubric if ev else None,
            "signals": ev.signals if ev else None,
            "recruiter": brief.summary.get("recruiter") if brief else None,
        }
    if len(role_ids) > 1:
        raise HTTPException(
            409, "cross-role comparison refused: candidates are on different roles"
        )
    return out
