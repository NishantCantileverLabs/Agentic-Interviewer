"""Question bank, role configs, and interview plans.

The backend decides what gets asked: a session points at a plan, the plan
references question ids, and the candidate-facing endpoint serves only the
statement + visible tests. Hidden-test expected outputs never appear in any
response (CLAUDE.md invariant #5) — including admin reads.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import InterviewPlan, Question, RoleConfig, Session
from app.tenancy import (
    OrgContext,
    ensure_session_access,
    get_db,
    get_org_context,
    log_admin_action,
    require_role,
)

router = APIRouter()


# ── questions ────────────────────────────────────────────────────────


class QuestionIn(BaseModel):
    title: str
    statement_md: str
    language_targets: list[str]
    visible_tests: dict[str, Any]
    hidden_tests: dict[str, Any]
    hints: dict[str, Any]  # {"levels": [nudge, direction, partial]}
    twist: dict[str, Any] | None = None
    difficulty: int = 1
    reference_solution: str | None = None  # write-only: never in responses


def _shape_question(q: Question, include_statement: bool = True) -> dict[str, Any]:
    """Response shape shared by all reads: hidden cases exposed as count only."""
    out: dict[str, Any] = {
        "id": str(q.id),
        "title": q.title,
        "language_targets": q.language_targets,
        "visible_tests": q.visible_tests,
        "hidden_test_count": len((q.hidden_tests or {}).get("cases", [])),
        "hint_levels": len((q.hints or {}).get("levels", [])),
        "has_twist": q.twist is not None,
        "difficulty": q.difficulty,
    }
    if include_statement:
        out["statement_md"] = q.statement_md
    return out


@router.post("/questions", status_code=201)
def create_question(
    body: QuestionIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("recruiter")),
) -> dict[str, Any]:
    levels = (body.hints or {}).get("levels", [])
    if len(levels) != 3:
        raise HTTPException(
            422, "hints.levels must have exactly 3 entries (nudge|direction|partial)"
        )
    q = Question(id=uuid.uuid4(), org_id=ctx.org_id, **body.model_dump())
    db.add(q)
    log_admin_action(db, ctx, "question_created", {"question_id": str(q.id), "title": q.title})
    db.commit()
    return _shape_question(q)


@router.get("/questions")
def list_questions(
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> list[dict[str, Any]]:
    # Question-bank listing is org-side; candidates get their round's question
    # via the session-scoped endpoint only.
    return [_shape_question(q, include_statement=False) for q in db.scalars(select(Question))]


# ── role configs & plans ─────────────────────────────────────────────


class RoleConfigIn(BaseModel):
    name: str
    competencies: dict[str, Any]
    weights: dict[str, Any]
    thresholds: dict[str, Any]


@router.post("/role-configs", status_code=201)
def create_role_config(
    body: RoleConfigIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("admin")),
) -> dict[str, str]:
    """Admin-only: role configs carry weights + thresholds — they alter hire
    signals, so changes are audit-logged (PHASE2 Track A)."""
    rc = RoleConfig(id=uuid.uuid4(), org_id=ctx.org_id, **body.model_dump())
    db.add(rc)
    log_admin_action(
        db, ctx, "role_config_created",
        {"role_config_id": str(rc.id), "name": rc.name, "thresholds": rc.thresholds},
    )
    db.commit()
    return {"id": str(rc.id)}


@router.get("/role-configs")
def list_role_configs(
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> list[dict[str, Any]]:
    return [
        {"id": str(rc.id), "name": rc.name, "weights": rc.weights, "thresholds": rc.thresholds}
        for rc in db.scalars(select(RoleConfig))
    ]


class PlanIn(BaseModel):
    role_config_id: uuid.UUID
    plan: dict[str, Any]  # PHASE1_ARCHITECTURE §6.2 schema


@router.post("/plans", status_code=201)
def create_plan(
    body: PlanIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("recruiter")),
) -> dict[str, str]:
    if db.get(RoleConfig, body.role_config_id) is None:
        raise HTTPException(404, "role config not found")
    coding_ref = body.plan.get("question_refs", {}).get("coding")
    if coding_ref and db.get(Question, uuid.UUID(coding_ref)) is None:
        raise HTTPException(422, f"plan references unknown coding question {coding_ref}")
    from app.models_phase23 import CasePack, DesignQuestion
    from app.rounds.registry import ROUND_TYPES

    content_requirements = {"coding": "question", "sql": "question",
                            "case": "case_pack", "system_design": "design_question"}
    for r in body.plan.get("rounds", []):
        if not r.get("id") or not r.get("type"):
            raise HTTPException(422, f"round missing id/type: {r}")
        if r["type"] not in ROUND_TYPES:
            raise HTTPException(422, f"unknown round type {r['type']!r}")
        q_ref = r.get("question")
        if q_ref and db.get(Question, uuid.UUID(str(q_ref))) is None:
            raise HTTPException(422, f"round {r['id']} references unknown question {q_ref}")
        if r.get("case_pack") and db.get(CasePack, uuid.UUID(str(r["case_pack"]))) is None:
            raise HTTPException(422, f"round {r['id']} references unknown case pack")
        if (
            r.get("design_question")
            and db.get(DesignQuestion, uuid.UUID(str(r["design_question"]))) is None
        ):
            raise HTTPException(422, f"round {r['id']} references unknown design question")
        need = content_requirements.get(r["type"])
        if need and not r.get(need):
            raise HTTPException(422, f"round {r['id']} ({r['type']}) needs a {need}")
    p = InterviewPlan(
        id=uuid.uuid4(), org_id=ctx.org_id, role_config_id=body.role_config_id, plan=body.plan
    )
    db.add(p)
    log_admin_action(db, ctx, "plan_created", {"plan_id": str(p.id)})
    db.commit()
    return {"id": str(p.id)}


@router.get("/plans")
def list_plans(
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> list[dict[str, Any]]:
    return [
        {
            "id": str(p.id),
            "role_config_id": str(p.role_config_id),
            "version": p.version,
            "plan": p.plan,
        }
        for p in db.scalars(select(InterviewPlan))
    ]


# ── candidate-facing question resolution (plan-driven rounds) ────────


def _plan_rounds(plan_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Rounds list, synthesizing the classic sequence for legacy plans."""
    if "rounds" in plan_json:
        return list(plan_json["rounds"])
    budgets = plan_json.get("time_budget_min", {})
    coding_q = (plan_json.get("question_refs") or {}).get("coding")
    legacy = [
        ("INTRO", "intro", 2), ("WARMUP", "warmup", 5),
        ("TECHNICAL_DEEPDIVE", "discussion", 12), ("CODING", "coding", 22),
        ("WRAPUP", "wrapup", 4),
    ]
    return [
        {
            "id": rid,
            "type": type_,
            "minutes": budgets.get(rid, default_min),
            "question": coding_q if type_ == "coding" else None,
        }
        for rid, type_, default_min in legacy
    ]


def _session_plan(session: Session, db: DbSession) -> InterviewPlan:
    if session.plan_id is None:
        raise HTTPException(409, "session has no interview plan attached")
    plan = db.get(InterviewPlan, session.plan_id)
    if plan is None:
        raise HTTPException(500, "session references a missing plan")
    return plan


@router.get("/sessions/{session_id}/questions")
def session_questions(
    session_id: uuid.UUID,
    include_hints: bool = False,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
) -> dict[str, Any]:
    ensure_session_access(ctx, session_id)
    if include_hints and ctx.role == "candidate":
        raise HTTPException(403, "hints are not candidate-visible")
    """All round-bound questions for this session, keyed by round id
    (statement + visible tests only). Used by the agent worker at bootstrap.
    `include_hints=1` additionally returns hint levels + twist prompt — for
    the agent worker only, never rendered to the candidate. Hidden-test
    expected outputs are excluded regardless (invariant #5)."""
    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    plan = _session_plan(session, db)
    out: dict[str, Any] = {}
    for r in _plan_rounds(plan.plan):
        if not r.get("question"):
            continue
        q = db.get(Question, uuid.UUID(str(r["question"])))
        if q is None:
            continue
        shaped = {**_shape_question(q), "round_type": r["type"]}
        if include_hints:
            shaped["hints"] = (q.hints or {}).get("levels", [])
            shaped["twist"] = (q.twist or {}).get("prompt") if q.twist else None
        out[str(r["id"])] = shaped
    return out


@router.get("/sessions/{session_id}/question")
def session_question(
    session_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
) -> dict[str, Any]:
    ensure_session_access(ctx, session_id)
    """The CURRENT round's question (statement + visible tests only), derived
    from the latest state_transition in the event log — fully backend-decided
    and auditable. Before any code round starts, previews the first one."""
    from app.models import InterviewEvent

    session = db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    plan = _session_plan(session, db)
    rounds = _plan_rounds(plan.plan)

    from sqlalchemy import select

    current_round_id: str | None = db.scalar(
        select(InterviewEvent.payload["to"].astext)
        .where(
            InterviewEvent.session_id == session_id,
            InterviewEvent.type == "state_transition",
        )
        .order_by(InterviewEvent.seq.desc())
        .limit(1)
    )
    target = next((r for r in rounds if r["id"] == current_round_id and r.get("question")), None)
    if target is None:
        target = next((r for r in rounds if r.get("question")), None)
    if target is None:
        raise HTTPException(409, "plan assigns no question to any round")
    q = db.get(Question, uuid.UUID(str(target["question"])))
    if q is None:
        raise HTTPException(500, "plan references a missing question")
    return {
        **_shape_question(q),
        "round_id": target["id"],
        "round_type": target["type"],
        "is_current_round": target["id"] == current_round_id,
        "language_default": plan.plan.get("language_default", "python"),
    }
