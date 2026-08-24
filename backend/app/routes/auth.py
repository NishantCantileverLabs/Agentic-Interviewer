"""Accounts: email+password+OTP signup, password login, Google sign-in.

Identity is global (users table, no RLS); org access comes from memberships.
Two account types map to the two platform surfaces:
- staff (recruiter/admin) -> /admin console; membership row grants the role
- candidate               -> /portal; matched to candidacies by email

Session tokens are HS256 JWTs (settings.session_secret). tenancy.get_org_context
resolves `Authorization: Bearer` into an OrgContext, so every existing role
gate (require_role) applies unchanged.

Dev ergonomics: with RESEND_API_KEY unset the OTP cannot be emailed, so
/auth/register returns it as `dev_otp` — that field disappears the moment a
real email key is configured.
"""

import hashlib
import hmac
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.db import SessionLocal, set_rls_context
from app.models import Membership, Org, Session, User
from app.models_phase23 import Candidacy, JobRole, Schedule, StaffInvite
from app.notify import send_email
from app.tenancy import DEFAULT_ORG_ID

router = APIRouter(prefix="/auth")

_GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"


# ── password + OTP hashing (stdlib scrypt; no plaintext at rest) ─────


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt_hex, digest_hex = stored.split("$", 2)
    digest = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def _otp_hash(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


# ── session tokens ───────────────────────────────────────────────────


def mint_session_token(user: User, role: str, org_id: uuid.UUID | None) -> str:
    settings = get_settings()
    return jwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "name": user.name,
            "typ": user.account_type,
            "role": role,
            "org": str(org_id) if org_id else None,
            "exp": int(time.time()) + settings.session_ttl_h * 3600,
        },
        settings.session_secret,
        algorithm="HS256",
    )


def decode_session_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, get_settings().session_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "session expired — log in again") from None
    except jwt.InvalidTokenError:
        raise HTTPException(401, "invalid session token") from None


def _identity_db() -> DbSession:
    """Identity operations manage global tables (users/memberships) and, for
    the candidate home, read the candidate's own rows across orgs — a
    deliberate, email-scoped bypass."""
    db = SessionLocal()
    set_rls_context(db, bypass=True)
    return db


def _staff_role(db: DbSession, user: User) -> tuple[str, uuid.UUID | None]:
    m = db.scalar(select(Membership).where(Membership.user_id == user.id).limit(1))
    if m:
        return m.role, m.org_id
    return ("candidate", None) if user.account_type == "candidate" else ("recruiter", None)


def _auth_response(db: DbSession, user: User) -> dict[str, Any]:
    role, org_id = ("candidate", None) if user.account_type == "candidate" else _staff_role(db, user)
    return {
        "token": mint_session_token(user, role, org_id),
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "account_type": user.account_type,
            "role": role,
        },
    }


def _staff_invite_for(db: DbSession, email: str) -> StaffInvite | None:
    return db.scalar(
        select(StaffInvite).where(func.lower(StaffInvite.email) == email.lower()).limit(1)
    )


def _org_has_members(db: DbSession) -> bool:
    return db.scalar(select(Membership).limit(1)) is not None


def _assert_staff_signup_allowed(db: DbSession, email: str) -> None:
    """Staff accounts are invite-only. The single exception: an org with no
    members yet — the first account bootstraps as the owning admin."""
    if _org_has_members(db) and _staff_invite_for(db, email) is None:
        raise HTTPException(
            403,
            "recruiter accounts are invite-only — ask an admin of your organization "
            "to invite this email from Settings",
        )


def _ensure_staff_membership(db: DbSession, user: User) -> None:
    """Grant org access per the invite (or bootstrap the first admin)."""
    if user.account_type != "staff":
        return
    exists = db.scalar(select(Membership).where(Membership.user_id == user.id).limit(1))
    if exists:
        return
    invite = _staff_invite_for(db, user.email)
    if invite is not None:
        db.add(Membership(user_id=user.id, org_id=invite.org_id, role=invite.role))
        invite.accepted_at = datetime.now(UTC)
    elif not _org_has_members(db):
        # first account in an empty org: the owner
        db.add(Membership(user_id=user.id, org_id=DEFAULT_ORG_ID, role="admin"))
    else:
        raise HTTPException(
            403,
            "recruiter accounts are invite-only — ask an admin of your organization "
            "to invite this email from Settings",
        )


# ── register / verify / login ────────────────────────────────────────


class _EmailModel(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _email_shape(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1] or " " in v:
            raise ValueError("invalid email address")
        return v


class RegisterIn(_EmailModel):
    name: str
    password: str
    account_type: str = "candidate"  # candidate | staff


@router.post("/register")
def register(body: RegisterIn) -> dict[str, Any]:
    if body.account_type not in ("candidate", "staff"):
        raise HTTPException(422, "account_type must be candidate or staff")
    if len(body.password) < 8:
        raise HTTPException(422, "password must be at least 8 characters")
    settings = get_settings()
    db = _identity_db()
    try:
        # fail invite-only staff signups BEFORE the OTP round-trip
        if body.account_type == "staff":
            _assert_staff_signup_allowed(db, body.email)
        email = body.email.lower()
        user = db.scalar(select(User).where(User.email == email))
        if user and user.email_verified:
            raise HTTPException(409, "an account with this email exists — log in instead")
        if user is None:
            user = User(id=uuid.uuid4(), email=email)
            db.add(user)
        user.name = body.name
        user.password_hash = hash_password(body.password)
        user.auth_provider = "password"
        user.account_type = body.account_type
        otp = f"{secrets.randbelow(1_000_000):06d}"
        user.otp_hash = _otp_hash(otp)
        user.otp_expires_at = datetime.now(UTC) + timedelta(minutes=settings.otp_ttl_min)
        db.commit()
        sent = send_email(
            email,
            "Your verification code",
            f"<p>Hi {body.name},</p><p>Your verification code is <b>{otp}</b>. "
            f"It expires in {settings.otp_ttl_min} minutes.</p>",
        )
        # dev-only convenience: surfaces the OTP when no email provider is
        # configured. Hard-off in production regardless of email config —
        # an unverifiable signup there is a config error, not a fallback.
        expose = not sent and settings.environment != "production"
        return {"otp_sent": sent, "dev_otp": otp if expose else None}
    finally:
        db.close()


class VerifyIn(_EmailModel):
    otp: str


# Brute-force guard: a 6-digit code gets 5 guesses, then the pending OTP is
# invalidated and registration must restart. In-memory (resets on restart) —
# the OTP itself expires in minutes, so persistence buys nothing here.
_OTP_ATTEMPTS: dict[str, int] = {}
_OTP_MAX_ATTEMPTS = 5


@router.post("/verify")
def verify_otp(body: VerifyIn) -> dict[str, Any]:
    db = _identity_db()
    try:
        email = body.email.lower()
        user = db.scalar(select(User).where(User.email == email))
        if user is None or user.otp_hash is None:
            raise HTTPException(404, "no pending verification for this email")
        if user.otp_expires_at is None or user.otp_expires_at < datetime.now(UTC):
            raise HTTPException(410, "code expired — register again to get a new one")
        if not hmac.compare_digest(user.otp_hash, _otp_hash(body.otp.strip())):
            attempts = _OTP_ATTEMPTS.get(email, 0) + 1
            _OTP_ATTEMPTS[email] = attempts
            if attempts >= _OTP_MAX_ATTEMPTS:
                user.otp_hash = None
                user.otp_expires_at = None
                db.commit()
                _OTP_ATTEMPTS.pop(email, None)
                raise HTTPException(
                    429, "too many incorrect codes — register again to get a new one"
                )
            raise HTTPException(401, "incorrect code")
        _OTP_ATTEMPTS.pop(email, None)
        user.email_verified = True
        user.otp_hash = None
        user.otp_expires_at = None
        _ensure_staff_membership(db, user)
        db.commit()
        return _auth_response(db, user)
    finally:
        db.close()


class LoginIn(_EmailModel):
    password: str


@router.post("/login")
def login(body: LoginIn) -> dict[str, Any]:
    db = _identity_db()
    try:
        user = db.scalar(select(User).where(User.email == body.email.lower()))
        if user is None or not verify_password(body.password, user.password_hash):
            raise HTTPException(401, "invalid email or password")
        if not user.email_verified:
            raise HTTPException(403, "email not verified — register again to get a code")
        return _auth_response(db, user)
    finally:
        db.close()


# ── Google sign-in (ID token from Google Identity Services) ──────────


class GoogleIn(BaseModel):
    credential: str
    account_type: str = "candidate"  # used only when the account is created


@router.post("/google")
def google_signin(body: GoogleIn) -> dict[str, Any]:
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(503, "Google sign-in is not configured (GOOGLE_CLIENT_ID)")
    try:
        signing_key = jwt.PyJWKClient(_GOOGLE_JWKS_URL).get_signing_key_from_jwt(
            body.credential
        )
        claims = jwt.decode(
            body.credential,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.google_client_id,
            issuer=["https://accounts.google.com", "accounts.google.com"],
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, f"invalid Google credential: {e}") from None
    email = str(claims.get("email", "")).lower()
    if not email or not claims.get("email_verified", False):
        raise HTTPException(401, "Google account has no verified email")
    db = _identity_db()
    try:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            if body.account_type not in ("candidate", "staff"):
                raise HTTPException(422, "account_type must be candidate or staff")
            user = User(
                id=uuid.uuid4(),
                email=email,
                name=str(claims.get("name") or email.split("@")[0]),
                auth_provider="google",
                auth_provider_id=str(claims.get("sub")),
                account_type=body.account_type,
                email_verified=True,
            )
            db.add(user)
        else:
            user.email_verified = True
            user.auth_provider_id = user.auth_provider_id or str(claims.get("sub"))
        _ensure_staff_membership(db, user)
        db.commit()
        return _auth_response(db, user)
    finally:
        db.close()


# ── who am I / candidate home ────────────────────────────────────────


def _bearer(request: Request) -> dict[str, Any]:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(401, "log in to continue")
    return decode_session_token(header.split(" ", 1)[1])


@router.get("/me")
def me(claims: dict[str, Any] = Depends(_bearer)) -> dict[str, Any]:
    return {
        "id": claims["sub"],
        "email": claims["email"],
        "name": claims.get("name"),
        "account_type": claims["typ"],
        "role": claims["role"],
    }


# ── self-serve demo interview ────────────────────────────────────────

DEMO_LIMIT = 3
_DEMO_COMPETENCIES = [
    {"id": "problem_solving", "weight": 0.3, "probe_budget": 2},
    {"id": "coding_proficiency", "weight": 0.3, "probe_budget": 2},
    {"id": "cs_fundamentals", "weight": 0.2, "probe_budget": 1},
    {"id": "communication", "weight": 0.2, "probe_budget": 1},
]
_TERMINAL = ("completed", "in_review", "reviewed", "withdrawn")


def _ensure_demo_plan(db: DbSession) -> uuid.UUID:
    """Idempotent: one short practice plan (marked role_config_id='demo' so it
    never becomes the default-interview fallback)."""
    from app.models import InterviewPlan, Question

    existing = db.scalar(
        select(InterviewPlan)
        .where(InterviewPlan.plan["role_config_id"].astext == "demo")
        .limit(1)
    )
    if existing is not None:
        return existing.id
    question = db.scalar(select(Question).where(Question.title == "Sum two ints").limit(1))
    coding: dict[str, Any] = {"id": "coding", "type": "coding", "minutes": 6}
    if question is not None:
        coding["question"] = str(question.id)
    plan = InterviewPlan(
        id=uuid.uuid4(),
        org_id=DEFAULT_ORG_ID,
        plan={
            "role_config_id": "demo",
            "rounds": [
                {"id": "intro", "type": "intro", "minutes": 1},
                {"id": "warmup", "type": "warmup", "minutes": 2},
                coding,
                {"id": "wrapup", "type": "wrapup", "minutes": 1},
            ],
            "competencies": _DEMO_COMPETENCIES,
            "language_default": "python",
        },
    )
    db.add(plan)
    db.commit()
    return plan.id


@router.post("/demo")
def start_demo(claims: dict[str, Any] = Depends(_bearer)) -> dict[str, Any]:
    """A ~10-minute practice interview any candidate account can take.
    In-flight demos are reused; hard cap per account."""
    if claims["typ"] != "candidate":
        raise HTTPException(403, "demo interviews are for candidate accounts")
    db = _identity_db()
    try:
        email = str(claims["email"])
        demos = db.scalars(
            select(Candidacy)
            .where(Candidacy.candidate_email == email, Candidacy.source == "demo")
            .order_by(Candidacy.created_at.desc())
        ).all()
        active = next((c for c in demos if c.status not in _TERMINAL), None)
        if active is not None:
            return {"candidacy_id": str(active.id), "portal_path": f"/i/{active.id}"}
        if len(demos) >= DEMO_LIMIT:
            raise HTTPException(409, "demo limit reached for this account")
        cand = Candidacy(
            id=uuid.uuid4(),
            org_id=DEFAULT_ORG_ID,
            candidate_email=email,
            candidate_name=str(claims.get("name") or email.split("@")[0]),
            source="demo",
            plan_id=_ensure_demo_plan(db),
        )
        db.add(cand)
        db.commit()
        return {"candidacy_id": str(cand.id), "portal_path": f"/i/{cand.id}"}
    finally:
        db.close()


@router.get("/me/interviews")
def my_interviews(claims: dict[str, Any] = Depends(_bearer)) -> list[dict[str, Any]]:
    """Candidate home: every candidacy addressed to the logged-in email, with
    its scheduled slot, role, and portal entry point."""
    if claims["typ"] != "candidate":
        raise HTTPException(403, "candidate accounts only")
    db = _identity_db()  # email-scoped cross-org read of the user's own rows
    try:
        rows = db.scalars(
            select(Candidacy)
            .where(Candidacy.candidate_email == claims["email"])
            .order_by(Candidacy.created_at.desc())
            .limit(50)
        ).all()
        out: list[dict[str, Any]] = []
        for c in rows:
            schedule = db.scalar(
                select(Schedule)
                .where(Schedule.candidacy_id == c.id)
                .order_by(Schedule.slot_start.desc())
                .limit(1)
            )
            role = db.get(JobRole, c.job_role_id) if c.job_role_id else None
            org = db.get(Org, c.org_id)
            latest_session = db.scalar(
                select(Session)
                .where(Session.candidacy_id == c.id)
                .order_by(Session.created_at.desc())
                .limit(1)
            )
            out.append(
                {
                    "candidacy_id": str(c.id),
                    "org_name": org.name if org else "—",
                    "source": c.source,
                    "role_name": role.name if role else None,
                    "status": c.status,
                    "slot_start": schedule.slot_start.isoformat() if schedule else None,
                    "session_status": latest_session.status if latest_session else None,
                    "portal_path": f"/candidate/{c.id}",
                }
            )
        return out
    finally:
        db.close()
