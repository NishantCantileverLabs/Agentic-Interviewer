"""T26 — multi-round pipelines: sittings, gates, orchestration; T27 endpoint.

Rounds: [{round_type, plan_ref?, question?/case_pack?/design_question?,
duration_min, sitting, gate: none|auto|review, weight}]. Each pipeline round
becomes its own single-round session (plan synthesized around it); gates
decide advancement — auto gates compute in code, review gates block on the
Phase 2 queue.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.eval.brief import DEFAULT_THRESHOLDS
from app.models import Evaluation, InterviewPlan, RoleConfig, Session
from app.models_phase23 import AggregateBrief, Candidacy, CandidacyProgress, Pipeline
from app.rounds.registry import ROUND_TYPES
from app.tenancy import (
    OrgContext,
    get_db,
    get_org_context,
    log_admin_action,
    mint_candidate_token,
    require_role,
)

router = APIRouter()


class PipelineIn(BaseModel):
    name: str
    role_config_id: uuid.UUID | None = None
    rounds: list[dict[str, Any]]


@router.post("/pipelines", status_code=201)
def create_pipeline(
    body: PipelineIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("recruiter")),
) -> dict[str, str]:
    if not body.rounds:
        raise HTTPException(422, "pipeline needs at least one round")
    for i, r in enumerate(body.rounds):
        if r.get("round_type") not in ROUND_TYPES:
            raise HTTPException(422, f"round {i}: unknown round_type {r.get('round_type')!r}")
        r.setdefault("duration_min", 20)
        r.setdefault("sitting", 1)
        r.setdefault("gate", "none")
        r.setdefault("weight", 1.0)
        if r["gate"] not in ("none", "auto", "review"):
            raise HTTPException(422, f"round {i}: invalid gate {r['gate']!r}")
    p = Pipeline(
        id=uuid.uuid4(), org_id=ctx.org_id, name=body.name,
        role_config_id=body.role_config_id, rounds=body.rounds,
    )
    db.add(p)
    log_admin_action(db, ctx, "pipeline_created", {"id": str(p.id), "name": body.name})
    db.commit()
    return {"id": str(p.id)}


@router.get("/pipelines")
def list_pipelines(
    db: DbSession = Depends(get_db), ctx: OrgContext = Depends(require_role("reviewer"))
) -> list[dict[str, Any]]:
    return [
        {"id": str(p.id), "name": p.name, "rounds": p.rounds}
        for p in db.scalars(select(Pipeline))
    ]


def _round_plan(db: DbSession, org_id: uuid.UUID, r: dict[str, Any], index: int) -> InterviewPlan:
    """Synthesize a single-round plan around a pipeline round definition."""
    competencies = [
        {"id": "problem_solving", "weight": 0.3, "probe_budget": 3},
        {"id": "coding_proficiency", "weight": 0.3, "probe_budget": 3},
        {"id": "cs_fundamentals", "weight": 0.2, "probe_budget": 2},
        {"id": "communication", "weight": 0.2, "probe_budget": 2},
    ]
    round_entry: dict[str, Any] = {
        "id": f"r{index}", "type": r["round_type"], "minutes": r["duration_min"],
    }
    for key in ("question", "case_pack", "design_question", "sql_dataset"):
        if r.get(key):
            round_entry[key] = r[key]
    plan = InterviewPlan(
        id=uuid.uuid4(),
        org_id=org_id,
        plan={
            "role_config_id": "pipeline",
            "rounds": [
                {"id": "intro", "type": "intro", "minutes": 1},
                round_entry,
                {"id": "wrapup", "type": "wrapup", "minutes": 1},
            ],
            "competencies": competencies,
        },
    )
    db.add(plan)
    return plan


class StartPipelineIn(BaseModel):
    pipeline_id: uuid.UUID


@router.post("/candidacies/{candidacy_id}/start-pipeline")
def start_pipeline(
    candidacy_id: uuid.UUID,
    body: StartPipelineIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("recruiter")),
) -> dict[str, Any]:
    cand = db.get(Candidacy, candidacy_id)
    pipe = db.get(Pipeline, body.pipeline_id)
    if cand is None or pipe is None:
        raise HTTPException(404, "candidacy or pipeline not found")
    if db.get(CandidacyProgress, candidacy_id) is not None:
        raise HTTPException(409, "pipeline already started for this candidacy")
    db.add(
        CandidacyProgress(
            candidacy_id=candidacy_id, org_id=cand.org_id, pipeline_id=pipe.id,
            current_round=0, round_sessions={}, gate_state="advancing",
        )
    )
    db.commit()
    return _advance(db, ctx, candidacy_id)


@router.post("/candidacies/{candidacy_id}/advance")
def advance_pipeline(
    candidacy_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
) -> dict[str, Any]:
    return _advance(db, ctx, candidacy_id)


def _advance(db: DbSession, ctx: OrgContext, candidacy_id: uuid.UUID) -> dict[str, Any]:
    """Orchestrator: evaluate the gate for the finished round (if any), then
    create the next round's session, or finish the pipeline."""
    prog = db.get(CandidacyProgress, candidacy_id)
    cand = db.get(Candidacy, candidacy_id)
    if prog is None or cand is None:
        raise HTTPException(404, "no pipeline in progress")
    pipe = db.get(Pipeline, prog.pipeline_id)
    if pipe is None:
        raise HTTPException(500, "progress references a missing pipeline")
    rounds: list[dict[str, Any]] = list(pipe.rounds)

    if prog.gate_state in ("ended", "completed"):
        return {"gate_state": prog.gate_state, "round_sessions": prog.round_sessions}

    # Gate check on the round just finished (current_round-1)
    finished_idx = prog.current_round - 1
    if finished_idx >= 0:
        gate = rounds[finished_idx].get("gate", "none")
        sid = prog.round_sessions.get(str(finished_idx))
        if sid is None:
            raise HTTPException(409, "previous round session missing")
        session = db.get(Session, uuid.UUID(sid))
        if session is None or session.status != "completed":
            raise HTTPException(409, "previous round not completed yet")
        if gate == "auto":
            passed = _auto_gate_passes(db, uuid.UUID(sid), pipe)
            if not passed:
                prog.gate_state = "ended"
                cand.status = "reviewed"
                db.commit()
                return {"gate_state": "ended", "reason": "auto gate below threshold"}
        elif gate == "review":
            from app.models_phase23 import ReviewDecision

            decision = db.scalar(
                select(ReviewDecision)
                .where(ReviewDecision.session_id == uuid.UUID(sid))
                .order_by(ReviewDecision.ts.desc())
                .limit(1)
            )
            if decision is None:
                prog.gate_state = "awaiting_review"
                db.commit()
                return {"gate_state": "awaiting_review",
                        "reason": "review-gate: queue decision required"}
            if decision.decision == "override":
                prog.gate_state = "ended"
                cand.status = "reviewed"
                db.commit()
                return {"gate_state": "ended", "reason": "review gate: overridden (no-advance)"}
        prog.gate_state = "advancing"

    if prog.current_round >= len(rounds):
        prog.gate_state = "completed"
        cand.status = "completed"
        db.commit()
        return {"gate_state": "completed", "round_sessions": prog.round_sessions}

    r = rounds[prog.current_round]
    plan = _round_plan(db, cand.org_id, r, prog.current_round)
    # voice picked in round 1's lobby carries across the pipeline — the
    # interviewer shouldn't change voice between rounds
    prior_voice = db.scalars(
        select(Session.voice)
        .where(Session.candidacy_id == cand.id, Session.voice.is_not(None))
        .order_by(Session.created_at.desc())
        .limit(1)
    ).first()
    session = Session(
        id=uuid.uuid4(), org_id=cand.org_id, candidacy_id=cand.id,
        candidate_label=cand.candidate_name, plan_id=plan.id,
        jd_text=cand.jd_text, resume_text=cand.resume_text,
        round_type=r["round_type"], pipeline_round_index=prog.current_round,
        voice=prior_voice,
    )
    db.add(session)
    token, jti = mint_candidate_token(session.id, cand.org_id)
    session.candidate_jti = jti
    prog.round_sessions = {**prog.round_sessions, str(prog.current_round): str(session.id)}
    prog.current_round += 1
    db.commit()
    return {
        "gate_state": "advancing",
        "round_index": prog.current_round - 1,
        "round_type": r["round_type"],
        "sitting": r.get("sitting", 1),
        "session_id": str(session.id),
        "interview_path": f"/interview?session={session.id}&candidate_token={token}",
    }


def _auto_gate_passes(db: DbSession, session_id: uuid.UUID, pipe: Pipeline) -> bool:
    """Auto gate: hire signal computed in code (never the LLM)."""
    ev = db.scalar(
        select(Evaluation).where(Evaluation.session_id == session_id)
        .order_by(Evaluation.version.desc()).limit(1)
    )
    if ev is None:
        raise HTTPException(409, "auto gate: evaluation not ready yet")
    rc = db.get(RoleConfig, pipe.role_config_id) if pipe.role_config_id else None
    thresholds = {**DEFAULT_THRESHOLDS, **((rc.thresholds or {}) if rc else {})}
    weights = dict(rc.weights) if rc and rc.weights else {}
    comps = ev.rubric.get("competencies", {})
    scored = {c: e for c, e in comps.items() if isinstance(e.get("score_1_to_5"), int)}
    if not scored:
        return False
    total = sum(weights.get(c, 1.0) for c in scored) or 1.0
    weighted = sum(e["score_1_to_5"] * weights.get(c, 1.0) for c, e in scored.items()) / total
    return bool(weighted >= float(thresholds.get("hire", 3.6)))


@router.post("/candidacies/{candidacy_id}/aggregate-brief")
async def generate_aggregate_brief(
    candidacy_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("recruiter")),
) -> dict[str, Any]:
    """T27: cross-round roll-up + consistency + HTML."""
    prog = db.get(CandidacyProgress, candidacy_id)
    cand = db.get(Candidacy, candidacy_id)
    if prog is None or cand is None:
        raise HTTPException(404, "no pipeline for this candidacy")
    pipe = db.get(Pipeline, prog.pipeline_id)
    if pipe is None:
        raise HTTPException(500, "progress references a missing pipeline")
    from app.eval.aggregate import build_aggregate, render_aggregate_html

    rc = db.get(RoleConfig, pipe.role_config_id) if pipe.role_config_id else None
    agg = await build_aggregate(
        db, candidacy_id, list(pipe.rounds), prog.round_sessions,
        thresholds=(rc.thresholds if rc else None),
    )
    version = (
        db.scalar(
            select(AggregateBrief.version)
            .where(AggregateBrief.candidacy_id == candidacy_id)
            .order_by(AggregateBrief.version.desc()).limit(1)
        ) or 0
    ) + 1
    html_doc = render_aggregate_html(cand.candidate_name, agg)
    object_name = f"{candidacy_id}/aggregate-v{version}.html"
    key: str | None = object_name
    try:
        import io

        from minio import Minio

        settings = get_settings()
        client = Minio(
            settings.s3_endpoint.replace("http://", "").replace("https://", ""),
            access_key=settings.s3_access_key, secret_key=settings.s3_secret_key,
            secure=settings.s3_endpoint.startswith("https"),
        )
        data = html_doc.encode()
        client.put_object(
            "briefs", object_name, io.BytesIO(data), len(data), content_type="text/html"
        )
    except Exception:  # noqa: BLE001 - JSON result still returned
        key = None
    row = AggregateBrief(
        id=uuid.uuid4(), org_id=cand.org_id, candidacy_id=candidacy_id,
        version=version, rollup=agg, consistency=agg.get("consistency", []),
        html_object_key=key,
    )
    db.add(row)
    db.commit()
    return {"id": str(row.id), "version": version, "rollup": agg}
