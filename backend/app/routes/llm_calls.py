import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import LLMCall, PromptVersion, Session
from app.tenancy import OrgContext, get_db, require_role

router = APIRouter()


class LLMCallIn(BaseModel):
    session_id: uuid.UUID | None = None
    prompt_version_name: str  # e.g. "conduct/coding_v1" — resolved to the newest matching row
    role: str
    model: str
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    ttft_ms: int | None = None
    total_ms: int | None = None
    cost_estimate: float | None = None


@router.post("/llm-calls", status_code=201)
def record_llm_call(
    body: LLMCallIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("reviewer", "service")),
) -> dict[str, int]:
    """Invariant #2: every LLM call logs here with a real prompt_version_id.
    Writers: the agent worker (service key) and org tooling — never anonymous."""
    org_id = ctx.org_id
    if body.session_id is not None:
        session = db.get(Session, body.session_id)
        if session is not None:
            org_id = session.org_id
    pv_id = db.scalar(
        select(PromptVersion.id)
        .where(PromptVersion.name == body.prompt_version_name)
        .order_by(PromptVersion.created_at.desc())
        .limit(1)
    )
    if pv_id is None:
        raise HTTPException(
            422,
            f"unknown prompt version {body.prompt_version_name!r} — run scripts/sync_prompts.py",
        )
    row = LLMCall(
        org_id=org_id,
        session_id=body.session_id,
        prompt_version_id=pv_id,
        role=body.role,
        model=body.model,
        input_tokens=body.input_tokens,
        cached_tokens=body.cached_tokens,
        output_tokens=body.output_tokens,
        ttft_ms=body.ttft_ms,
        total_ms=body.total_ms,
        cost_estimate=body.cost_estimate,
    )
    db.add(row)
    db.commit()
    return {"id": row.id}
