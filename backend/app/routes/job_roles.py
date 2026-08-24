"""Job roles: what recruiters create interviews for, and hiring statistics.

A role binds a pipeline (multi-round) or a plan (single interview). Assigning
a candidacy to a role decides which interview the candidate gets when they
press start (lifecycle.start_interview consults it).
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.models import InterviewPlan, Session
from app.models_phase23 import Candidacy, JobRole, Pipeline
from app.tenancy import OrgContext, get_db, log_admin_action, require_role

router = APIRouter()


class JobRoleIn(BaseModel):
    name: str
    description: str | None = None
    pipeline_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None


@router.post("/job-roles", status_code=201)
def create_job_role(
    body: JobRoleIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("recruiter")),
) -> dict[str, Any]:
    if body.pipeline_id and db.get(Pipeline, body.pipeline_id) is None:
        raise HTTPException(404, "pipeline not found")
    if body.plan_id and db.get(InterviewPlan, body.plan_id) is None:
        raise HTTPException(404, "plan not found")
    role = JobRole(id=uuid.uuid4(), org_id=ctx.org_id, **body.model_dump())
    db.add(role)
    log_admin_action(db, ctx, "job_role_created", {"job_role_id": str(role.id), "name": body.name})
    db.commit()
    return {"id": str(role.id)}


@router.get("/job-roles")
def list_job_roles(
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> list[dict[str, Any]]:
    roles = db.scalars(select(JobRole).order_by(JobRole.created_at.desc())).all()
    counts: dict[uuid.UUID, int] = {
        row[0]: row[1]
        for row in db.execute(
            select(Candidacy.job_role_id, func.count(Candidacy.id))
            .where(Candidacy.job_role_id.is_not(None))
            .group_by(Candidacy.job_role_id)
        ).all()
        if row[0] is not None
    }
    out = []
    for r in roles:
        pipe = db.get(Pipeline, r.pipeline_id) if r.pipeline_id else None
        out.append(
            {
                "id": str(r.id),
                "name": r.name,
                "description": r.description,
                "status": r.status,
                "pipeline_id": str(r.pipeline_id) if r.pipeline_id else None,
                "pipeline_name": pipe.name if pipe else None,
                "plan_id": str(r.plan_id) if r.plan_id else None,
                "candidates": int(counts.get(r.id, 0)),
                "created_at": r.created_at.isoformat(),
            }
        )
    return out


class AssignRoleIn(BaseModel):
    job_role_id: uuid.UUID


@router.post("/candidacies/{candidacy_id}/assign-role")
def assign_role(
    candidacy_id: uuid.UUID,
    body: AssignRoleIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("recruiter")),
) -> dict[str, Any]:
    cand = db.get(Candidacy, candidacy_id)
    role = db.get(JobRole, body.job_role_id)
    if cand is None or role is None:
        raise HTTPException(404, "candidacy or job role not found")
    cand.job_role_id = role.id
    log_admin_action(
        db, ctx, "role_assigned",
        {"candidacy_id": str(candidacy_id), "job_role_id": str(role.id)},
    )
    db.commit()
    return {"assigned": role.name}


@router.get("/metrics/hiring")
def hiring_stats(
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer")),
) -> dict[str, Any]:
    """Recruiter statistics: counts are computed from candidacies + completed
    sessions (deterministic SQL — nothing inferred)."""
    total = db.scalar(select(func.count(Candidacy.id))) or 0
    interviewed_ids = {
        row[0]
        for row in db.execute(
            select(Session.candidacy_id)
            .where(Session.status == "completed", Session.candidacy_id.is_not(None))
            .distinct()
        ).all()
    }
    scheduled = db.scalar(
        select(func.count(Candidacy.id)).where(Candidacy.status == "scheduled")
    ) or 0

    by_role: list[dict[str, Any]] = []
    for role in db.scalars(select(JobRole).order_by(JobRole.created_at.desc())):
        cands = db.scalars(
            select(Candidacy.id).where(Candidacy.job_role_id == role.id)
        ).all()
        by_role.append(
            {
                "role_id": str(role.id),
                "role_name": role.name,
                "invited": len(cands),
                "interviewed": len([c for c in cands if c in interviewed_ids]),
            }
        )
    unassigned = db.scalars(
        select(Candidacy.id).where(Candidacy.job_role_id.is_(None))
    ).all()
    return {
        "total_candidates": int(total),
        "scheduled": int(scheduled),
        "interviewed": len(interviewed_ids),
        "by_role": by_role,
        "unassigned": {
            "invited": len(unassigned),
            "interviewed": len([c for c in unassigned if c in interviewed_ids]),
        },
    }
