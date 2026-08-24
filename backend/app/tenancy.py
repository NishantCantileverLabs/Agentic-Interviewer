"""T10 — org context resolution, role gates, and RLS plumbing.

Identity sources, in precedence order:
1. Candidate link JWT (?candidate_token= or X-Candidate-Token): 24h,
   single-session scope, revocable via sessions.candidate_jti.
2. Service key (X-Internal-Key): trusted workers (agent, eval) — RLS bypass
   with explicit intent; interim until per-job org context lands with T13.
3. Dev IdP stub (X-Org-Id / X-Role / X-User-Email headers) — the seam where
   Clerk/Auth0 plugs in: swap `_resolve_headers` for token verification, the
   rest of the app is untouched.
4. Default-org fallback (DEV only, settings.dev_default_org) so the Phase 1
   UI keeps working before org-aware login ships.

Every request's DB session runs `SET app.current_org` (and resets
app.bypass_rls) — pooled connections can never leak a previous request's org.
"""

import time
import uuid
from collections.abc import Callable, Generator
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.db import SessionLocal

DEFAULT_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

ROLE_RANK = {"reviewer": 1, "recruiter": 2, "admin": 3}


@dataclass(frozen=True)
class OrgContext:
    org_id: uuid.UUID
    role: str  # admin | recruiter | reviewer | candidate | service
    user_email: str
    session_scope: uuid.UUID | None = None  # candidate tokens: only this session
    bypass_rls: bool = False


def mint_candidate_token(session_id: uuid.UUID, org_id: uuid.UUID) -> tuple[str, str]:
    """Returns (jwt, jti). Persist jti on the session; re-minting revokes."""
    settings = get_settings()
    jti = uuid.uuid4().hex
    token = jwt.encode(
        {
            "sid": str(session_id),
            "org": str(org_id),
            "jti": jti,
            "exp": int(time.time()) + settings.candidate_link_ttl_h * 3600,
        },
        settings.candidate_link_secret,
        algorithm="HS256",
    )
    return token, jti


def _decode_candidate_token(token: str) -> dict[str, str]:
    try:
        return jwt.decode(
            token, get_settings().candidate_link_secret, algorithms=["HS256"]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "candidate link expired") from None
    except jwt.InvalidTokenError:
        raise HTTPException(401, "invalid candidate link") from None


def get_org_context(request: Request) -> OrgContext:
    settings = get_settings()

    token = request.query_params.get("candidate_token") or request.headers.get(
        "x-candidate-token"
    )
    if token:
        claims = _decode_candidate_token(token)
        return OrgContext(
            org_id=uuid.UUID(claims["org"]),
            role="candidate",
            user_email=f"candidate:{claims['sid']}",
            session_scope=uuid.UUID(claims["sid"]),
        )

    internal = request.headers.get("x-internal-key")
    if internal and internal == settings.internal_api_key:
        return OrgContext(
            org_id=DEFAULT_ORG_ID, role="service", user_email="service", bypass_rls=True
        )

    # Account session token (login/signup). Staff role/org are NOT trusted from
    # the token's claims — they are re-read from memberships on every request,
    # so revoking or downgrading someone takes effect immediately, not at
    # token expiry. Candidate-account tokens rank below every staff gate.
    bearer = request.headers.get("authorization", "")
    if bearer.lower().startswith("bearer "):
        from app.routes.auth import decode_session_token

        claims = decode_session_token(bearer.split(" ", 1)[1])
        email = str(claims.get("email", "unknown"))
        if claims.get("typ") == "candidate":
            return OrgContext(org_id=DEFAULT_ORG_ID, role="candidate", user_email=email)

        from app.models import Membership

        db = SessionLocal()
        try:
            db.execute(text("SELECT set_config('app.bypass_rls', 'on', false)"))
            membership = db.scalar(
                select(Membership)
                .where(Membership.user_id == uuid.UUID(str(claims["sub"])))
                .limit(1)
            )
        finally:
            db.close()
        if membership is None:
            raise HTTPException(403, "your access to this organization was removed")
        return OrgContext(
            org_id=membership.org_id, role=membership.role, user_email=email
        )

    org_header = request.headers.get("x-org-id")
    # Dev IdP stub: headers are attacker-controlled, so this path exists ONLY
    # outside production (real deployments use session/candidate tokens).
    if org_header and settings.environment != "production":
        try:
            org_id = uuid.UUID(org_header)
        except ValueError:
            raise HTTPException(400, "invalid X-Org-Id") from None
        role = request.headers.get("x-role", "admin")
        if role not in ROLE_RANK:
            raise HTTPException(400, f"invalid role {role!r}")
        return OrgContext(
            org_id=org_id,
            role=role,
            user_email=request.headers.get("x-user-email", "dev@local"),
        )

    if settings.dev_default_org:
        return OrgContext(org_id=DEFAULT_ORG_ID, role="admin", user_email="dev@local")
    # Anonymous: rank-0 "public" context. Candidate-portal endpoints (which
    # resolve access by candidacy id internally) keep working; every
    # require_role gate rejects it.
    return OrgContext(org_id=DEFAULT_ORG_ID, role="public", user_email="anonymous")


def get_db(
    ctx: OrgContext = Depends(get_org_context),
) -> Generator[DbSession, None, None]:
    """Org-scoped DB session: RLS context set on every acquisition."""
    db = SessionLocal()
    try:
        db.execute(
            text("SELECT set_config('app.current_org', :org, false)"),
            {"org": str(ctx.org_id)},
        )
        db.execute(
            text("SELECT set_config('app.bypass_rls', :b, false)"),
            {"b": "on" if ctx.bypass_rls else "off"},
        )
        yield db
    finally:
        db.close()


def require_role(*roles: str) -> Callable[..., OrgContext]:
    """Role gate. Roles rank reviewer < recruiter < admin; candidate/service
    are matched by name only."""

    def dependency(ctx: OrgContext = Depends(get_org_context)) -> OrgContext:
        if ctx.role in roles:
            return ctx
        min_rank = min((ROLE_RANK[r] for r in roles if r in ROLE_RANK), default=99)
        if ROLE_RANK.get(ctx.role, 0) >= min_rank:
            return ctx
        raise HTTPException(403, f"requires role {' or '.join(roles)}")

    return dependency


def ensure_session_access(ctx: OrgContext, session_id: uuid.UUID) -> None:
    """Session-scoped resources need a real identity: staff/service, or a
    candidate token pinned to exactly this session. Anonymous callers are
    rejected here regardless of which endpoint forgot its own gate."""
    if ctx.role == "public":
        raise HTTPException(403, "log in, or open this from your interview link")
    if ctx.role == "candidate" and ctx.session_scope != session_id:
        raise HTTPException(403, "this link is limited to a different session")


def log_admin_action(
    db: DbSession, ctx: OrgContext, action: str, payload: dict[str, object]
) -> None:
    from app.models import AdminAction

    db.add(
        AdminAction(
            org_id=ctx.org_id, user_email=ctx.user_email, action=action, payload=payload
        )
    )
