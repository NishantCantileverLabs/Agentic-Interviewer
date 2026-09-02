"""Invite-only staff accounts, pinned.

An org with members refuses uninvited staff signups; an invite admits with
the invited role; candidates are unaffected; the invite endpoints are
admin-gated. (First-user bootstrap isn't exercised here — the dev database
already has members, which is exactly the state that must reject strangers.)
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db import SessionLocal, set_rls_context
from app.main import app
from app.models import Membership, User
from app.models_phase23 import StaffInvite
from app.tenancy import DEFAULT_ORG_ID

ADMIN = {
    "X-Org-Id": str(DEFAULT_ORG_ID),
    "X-Role": "admin",
    "X-User-Email": "members-test@local",
}


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _cleanup(email: str) -> None:
    db = SessionLocal()
    set_rls_context(db, bypass=True)
    try:
        user = db.scalar(select(User).where(User.email == email))
        if user:
            db.execute(delete(Membership).where(Membership.user_id == user.id))
            db.delete(user)
        db.execute(delete(StaffInvite).where(StaffInvite.email == email))
        db.commit()
    finally:
        db.close()


def test_uninvited_staff_signup_rejected(client: TestClient) -> None:
    email = f"stranger-{uuid.uuid4().hex[:8]}@corp.test"
    resp = client.post(
        "/auth/register",
        json={"name": "Stranger", "email": email, "password": "password123",
              "account_type": "staff"},
    )
    assert resp.status_code == 403
    assert "invite" in resp.json()["detail"].lower()


def test_invited_staff_signup_gets_invited_role(client: TestClient) -> None:
    email = f"invited-{uuid.uuid4().hex[:8]}@corp.test"
    try:
        inv = client.post(
            "/org/members/invite", headers=ADMIN,
            json={"email": email, "role": "reviewer"},
        )
        assert inv.status_code == 201

        reg = client.post(
            "/auth/register",
            json={"name": "Invited", "email": email, "password": "password123",
                  "account_type": "staff"},
        )
        assert reg.status_code == 200
        otp = reg.json()["dev_otp"]
        assert otp, "dev_otp expected outside production"

        ver = client.post("/auth/verify", json={"email": email, "otp": otp})
        assert ver.status_code == 200
        assert ver.json()["user"]["role"] == "reviewer"
    finally:
        _cleanup(email)


def test_candidate_signup_needs_no_invite(client: TestClient) -> None:
    email = f"cand-{uuid.uuid4().hex[:8]}@mail.test"
    try:
        reg = client.post(
            "/auth/register",
            json={"name": "Cand", "email": email, "password": "password123",
                  "account_type": "candidate"},
        )
        assert reg.status_code == 200
    finally:
        _cleanup(email)


def test_member_endpoints_are_admin_gated(client: TestClient) -> None:
    from app.config import get_settings

    settings = get_settings()
    original = settings.dev_default_org
    settings.dev_default_org = False  # production semantics for "anonymous"
    try:
        assert client.get("/org/members").status_code == 403
        resp = client.post("/org/members/invite", json={"email": "x@y.test"})
        assert resp.status_code == 403
    finally:
        settings.dev_default_org = original
