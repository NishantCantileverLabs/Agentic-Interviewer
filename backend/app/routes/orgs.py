"""Org management (T10). Org creation is a platform-operator action; in dev
the header stub allows it, in production this sits behind the IdP's
platform-admin claim."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session as DbSession

from app.db import SessionLocal
from app.models import Org
from app.tenancy import OrgContext, get_org_context

router = APIRouter()


def _open_db() -> DbSession:
    # orgs table is not tenant-scoped (it IS the tenant registry)
    return SessionLocal()


class OrgIn(BaseModel):
    name: str
    settings: dict[str, Any] = {}


@router.post("/orgs", status_code=201)
def create_org(body: OrgIn) -> dict[str, str]:
    db = _open_db()
    try:
        if db.scalar(select(Org).where(Org.name == body.name)) is not None:
            raise HTTPException(409, f"org {body.name!r} already exists")
        org = Org(id=uuid.uuid4(), name=body.name, settings=body.settings)
        db.add(org)
        db.commit()
        return {"id": str(org.id), "name": org.name}
    finally:
        db.close()


@router.get("/orgs")
def list_orgs() -> list[dict[str, str]]:
    db = _open_db()
    try:
        return [{"id": str(o.id), "name": o.name} for o in db.scalars(select(Org))]
    finally:
        db.close()


@router.get("/me")
def whoami(ctx: OrgContext = Depends(get_org_context)) -> dict[str, Any]:
    return {
        "org_id": str(ctx.org_id),
        "role": ctx.role,
        "user_email": ctx.user_email,
        "session_scope": str(ctx.session_scope) if ctx.session_scope else None,
    }


@router.get("/orgs/current/admin-actions")
def list_admin_actions(
    ctx: OrgContext = Depends(get_org_context),
) -> list[dict[str, Any]]:
    db = _open_db()
    try:
        db.execute(
            text("SELECT set_config('app.current_org', :o, false)"),
            {"o": str(ctx.org_id)},
        )
        from app.models import AdminAction

        rows = db.scalars(
            select(AdminAction).order_by(AdminAction.ts.desc()).limit(100)
        )
        return [
            {
                "user": a.user_email,
                "action": a.action,
                "payload": a.payload,
                "ts": a.ts.isoformat(),
            }
            for a in rows
        ]
    finally:
        db.close()
