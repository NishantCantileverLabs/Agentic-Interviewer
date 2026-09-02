"""Phase 3 content routes: case packs, design questions, SQL datasets,
round-content bundle for the agent, tools for the candidate UI."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import InterviewPlan, Question, Session
from app.models_phase23 import CasePack, DesignQuestion, Resume, SqlDataset
from app.rounds.registry import ROUND_TYPES, tools_for
from app.rounds.resume_parser import find_contradictions, parse_resume
from app.tenancy import (
    OrgContext,
    ensure_session_access,
    get_db,
    get_org_context,
    log_admin_action,
    require_role,
)

router = APIRouter()


# ── content authoring ────────────────────────────────────────────────


class CasePackIn(BaseModel):
    title: str
    pack: dict[str, Any]


@router.post("/case-packs", status_code=201)
def create_case_pack(
    body: CasePackIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("recruiter")),
) -> dict[str, str]:
    required = ("prompt_md", "exhibits", "expected_structure", "math_blocks")
    missing = [k for k in required if k not in body.pack]
    if missing:
        raise HTTPException(422, f"case pack missing sections: {missing}")
    for block in body.pack.get("math_blocks", []):
        if "correct_value" not in block or "id" not in block:
            raise HTTPException(422, "each math_block needs id + correct_value")
    row = CasePack(id=uuid.uuid4(), org_id=ctx.org_id, title=body.title, pack=body.pack)
    db.add(row)
    log_admin_action(db, ctx, "case_pack_created", {"id": str(row.id), "title": body.title})
    db.commit()
    return {"id": str(row.id)}


@router.get("/case-packs")
def list_case_packs(
    db: DbSession = Depends(get_db), ctx: OrgContext = Depends(require_role("reviewer"))
) -> list[dict[str, Any]]:
    return [
        {"id": str(p.id), "title": p.title, "version": p.version}
        for p in db.scalars(select(CasePack))
    ]


class DesignQuestionIn(BaseModel):
    title: str
    requirement_sheet: dict[str, Any]
    reference_components: list[str]
    dive_areas: list[str]
    estimation_blocks: list[dict[str, Any]] = []


@router.post("/design-questions", status_code=201)
def create_design_question(
    body: DesignQuestionIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("recruiter")),
) -> dict[str, str]:
    row = DesignQuestion(
        id=uuid.uuid4(),
        title=body.title,
        requirement_sheet=body.requirement_sheet,
        reference_components=body.reference_components,
        dive_areas=body.dive_areas,
        estimation_blocks=body.estimation_blocks,
    )
    db.add(row)
    db.commit()
    return {"id": str(row.id)}


@router.get("/design-questions")
def list_design_questions(db: DbSession = Depends(get_db)) -> list[dict[str, Any]]:
    return [
        {"id": str(q.id), "title": q.title, "version": q.version}
        for q in db.scalars(select(DesignQuestion))
    ]


class SqlDatasetIn(BaseModel):
    title: str
    schema_ddl: str
    tasks: dict[str, Any]


@router.post("/sql-datasets", status_code=201)
def create_sql_dataset(
    body: SqlDatasetIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("recruiter")),
) -> dict[str, str]:
    row = SqlDataset(
        id=uuid.uuid4(), title=body.title, schema_ddl=body.schema_ddl, tasks=body.tasks
    )
    db.add(row)
    db.commit()
    return {"id": str(row.id)}


# ── agent bundle + candidate tools ───────────────────────────────────


def _plan_rounds(plan_json: dict[str, Any]) -> list[dict[str, Any]]:
    from app.routes.admin import _plan_rounds as legacy

    return legacy(plan_json)


@router.get("/sessions/{session_id}/round-content")
def round_content(
    session_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
) -> dict[str, Any]:
    """Everything the agent needs per round: statements, hints, case packs,
    design questions, behavioral claims. Service/staff only — packs contain
    reference answers."""
    if ctx.role == "candidate":
        raise HTTPException(403, "round content is not candidate-visible")
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    plan = db.get(InterviewPlan, session.plan_id) if session.plan_id else None
    rounds = _plan_rounds(plan.plan) if plan else []
    out: dict[str, Any] = {}
    for r in rounds:
        entry: dict[str, Any] = {"round_type": r["type"]}
        if r.get("question"):
            q = db.get(Question, uuid.UUID(str(r["question"])))
            if q:
                entry["statement"] = q.statement_md
                entry["hints"] = (q.hints or {}).get("levels", [])
                entry["twist"] = (q.twist or {}).get("prompt") if q.twist else None
        if r.get("case_pack"):
            p = db.get(CasePack, uuid.UUID(str(r["case_pack"])))
            if p:
                entry["case_pack"] = p.pack
        if r.get("design_question"):
            dq = db.get(DesignQuestion, uuid.UUID(str(r["design_question"])))
            if dq:
                entry["design_question"] = {
                    "requirement_sheet": dq.requirement_sheet,
                    "reference_components": dq.reference_components,
                    "dive_areas": dq.dive_areas,
                    "estimation_blocks": dq.estimation_blocks,
                }
        if r["type"] == "behavioral" and session.candidacy_id:
            resume = db.scalar(
                select(Resume)
                .where(Resume.candidacy_id == session.candidacy_id)
                .order_by(Resume.created_at.desc())
                .limit(1)
            )
            if resume:
                entry["unprobed_claims"] = resume.parsed_claims.get("quantified_claims", [])
                entry["contradictions"] = find_contradictions(resume.parsed_claims)
        elif r["type"] == "behavioral" and session.resume_text:
            parsed = parse_resume(session.resume_text)
            entry["unprobed_claims"] = parsed.get("quantified_claims", [])
            entry["contradictions"] = find_contradictions(parsed)
        out[str(r["id"])] = entry
    return out


@router.get("/sessions/{session_id}/tools")
def session_tools(
    session_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
) -> dict[str, Any]:
    """Tool panels for the CURRENT round (candidate UI = f(round type))."""
    from sqlalchemy import select as sel

    from app.models import InterviewEvent

    ensure_session_access(ctx, session_id)
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    plan = db.get(InterviewPlan, session.plan_id) if session.plan_id else None
    rounds = _plan_rounds(plan.plan) if plan else []
    current = db.scalar(
        sel(InterviewEvent.payload["to"].astext)
        .where(
            InterviewEvent.session_id == session_id,
            InterviewEvent.type == "state_transition",
        )
        .order_by(InterviewEvent.seq.desc())
        .limit(1)
    )
    r = next((x for x in rounds if x["id"] == current), rounds[0] if rounds else None)
    rtype = r["type"] if r else "warmup"
    return {
        "round_id": r["id"] if r else None,
        "round_type": rtype,
        "tools": list(tools_for(rtype)),
        "known_types": list(ROUND_TYPES),
    }
