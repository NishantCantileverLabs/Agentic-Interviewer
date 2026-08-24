"""A1 — org members: list, invite (staff accounts are invite-only), revoke.

Invites are the allow-list app/routes/auth.py checks at signup; revoking a
membership takes effect on the member's next request (tenancy re-reads
memberships per request — claims are never trusted)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.models import Membership, User
from app.models_phase23 import StaffInvite
from app.notify import send_email
from app.tenancy import OrgContext, get_db, log_admin_action, require_role

router = APIRouter()

INVITABLE_ROLES = ("reviewer", "recruiter", "admin")


@router.get("/org/members")
def list_members(
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("admin")),
) -> dict[str, Any]:
    members = []
    for m in db.scalars(select(Membership).where(Membership.org_id == ctx.org_id)):
        user = db.get(User, m.user_id)
        members.append(
            {
                "user_id": str(m.user_id),
                "email": user.email if user else "?",
                "name": user.name if user else None,
                "role": m.role,
            }
        )
    invites = [
        {
            "id": str(i.id),
            "email": i.email,
            "role": i.role,
            "invited_by": i.invited_by,
            "accepted": i.accepted_at is not None,
            "created_at": i.created_at.isoformat(),
        }
        for i in db.scalars(
            select(StaffInvite)
            .where(StaffInvite.org_id == ctx.org_id)
            .order_by(StaffInvite.created_at.desc())
        )
    ]
    return {"members": members, "invites": invites}


class MemberInviteIn(BaseModel):
    email: str
    role: str = "recruiter"


@router.post("/org/members/invite", status_code=201)
def invite_member(
    body: MemberInviteIn,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("admin")),
) -> dict[str, Any]:
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "invalid email address")
    if body.role not in INVITABLE_ROLES:
        raise HTTPException(422, f"role must be one of {INVITABLE_ROLES}")

    existing = db.scalar(
        select(StaffInvite).where(
            StaffInvite.org_id == ctx.org_id, func.lower(StaffInvite.email) == email
        )
    )
    if existing:
        existing.role = body.role  # re-invite updates the granted role
        existing.accepted_at = existing.accepted_at  # unchanged
        invite = existing
    else:
        invite = StaffInvite(
            id=uuid.uuid4(), org_id=ctx.org_id, email=email, role=body.role,
            invited_by=ctx.user_email,
        )
        db.add(invite)
    log_admin_action(db, ctx, "member_invited", {"email": email, "role": body.role})
    db.commit()

    link = f"{get_settings().app_base_url}/login"
    sent = send_email(
        email,
        "You're invited to the hiring console",
        f"<p>You've been invited as a {body.role}. "
        f'<a href="{link}">Sign up with this email address</a> to get access.</p>',
    )
    return {"id": str(invite.id), "email_sent": sent}


@router.delete("/org/members/invite/{invite_id}")
def revoke_invite(
    invite_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("admin")),
) -> dict[str, str]:
    invite = db.get(StaffInvite, invite_id)
    if invite is None:
        raise HTTPException(404, "invite not found")
    db.delete(invite)
    log_admin_action(db, ctx, "invite_revoked", {"email": invite.email})
    db.commit()
    return {"revoked": invite.email}


@router.delete("/org/members/{user_id}")
def remove_member(
    user_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    ctx: OrgContext = Depends(require_role("admin")),
) -> dict[str, str]:
    """Revoking access is immediate: role gates re-read memberships on every
    request. An admin cannot remove themself (no lock-outs)."""
    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == user_id, Membership.org_id == ctx.org_id
        )
    )
    if membership is None:
        raise HTTPException(404, "member not found")
    user = db.get(User, user_id)
    if user and user.email.lower() == ctx.user_email.lower():
        raise HTTPException(409, "you cannot remove your own access")
    # also drop any standing invite so they cannot immediately re-join
    now = datetime.now(UTC)
    for inv in db.scalars(
        select(StaffInvite).where(
            StaffInvite.org_id == ctx.org_id,
            func.lower(StaffInvite.email) == (user.email.lower() if user else ""),
        )
    ):
        db.delete(inv)
    db.delete(membership)
    log_admin_action(
        db, ctx, "member_removed",
        {"user_id": str(user_id), "email": user.email if user else "?", "at": now.isoformat()},
    )
    db.commit()
    return {"removed": user.email if user else str(user_id)}
