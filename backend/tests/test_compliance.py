"""Invariant #13 — erase()/export() stay correct as the schema grows.

Pins the two additions that postdate the original DSR implementation:
- users (candidate accounts, migration 0009): erased to tombstones, exported
- aggregate_briefs (migration 0008): quote-bearing rollups scrubbed on erase

Runs against the dev database (same DATABASE_URL the suite already uses).
"""

import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal, set_rls_context
from app.models import User
from app.models_phase23 import AggregateBrief, Candidacy
from app.routes.compliance import TOMBSTONE, erase_candidacy, export_candidacy
from app.tenancy import DEFAULT_ORG_ID, OrgContext

CTX = OrgContext(org_id=DEFAULT_ORG_ID, role="admin", user_email="test@compliance")


@pytest.fixture()
def db():
    session = SessionLocal()
    set_rls_context(session, bypass=True)
    yield session
    session.close()


@pytest.fixture()
def subject(db):
    """A candidacy with a candidate account and an aggregate brief."""
    email = f"dsr-{uuid.uuid4().hex[:8]}@compliance.test"
    cand = Candidacy(
        id=uuid.uuid4(), org_id=DEFAULT_ORG_ID,
        candidate_name="DSR Subject", candidate_email=email,
    )
    account = User(
        id=uuid.uuid4(), email=email, name="DSR Subject",
        password_hash="scrypt$00$00", account_type="candidate", email_verified=True,
    )
    rollup = AggregateBrief(
        id=uuid.uuid4(), org_id=DEFAULT_ORG_ID, candidacy_id=cand.id,
        rollup={"competencies": {"communication": {"evidence": ["a revealing quote"]}}},
        consistency=[{"claim": "quoted claim"}],
    )
    db.add(cand)
    db.commit()
    db.add_all([account, rollup])
    db.commit()
    yield cand, account, rollup
    # cleanup regardless of test outcome
    for table, col in (
        ("aggregate_briefs", "candidacy_id"),
        ("purge_audit", "subject"),
    ):
        db.execute(
            text(f"DELETE FROM {table} WHERE {col} = :v"),
            {"v": str(cand.id)},
        )
    db.execute(text("DELETE FROM candidacies WHERE id = :v"), {"v": str(cand.id)})
    db.execute(text("DELETE FROM users WHERE id = :v"), {"v": str(account.id)})
    db.commit()


def test_export_includes_account_and_aggregate_briefs(db, subject) -> None:
    cand, _account, _rollup = subject
    bundle = export_candidacy(cand.id, db, CTX)
    assert bundle["account"] is not None
    assert bundle["account"]["email"] == cand.candidate_email
    assert len(bundle["aggregate_briefs"]) == 1
    assert "communication" in str(bundle["aggregate_briefs"][0]["rollup"])


def test_erase_tombstones_account_and_scrubs_rollups(db, subject) -> None:
    cand, account, rollup = subject
    erase_candidacy(cand.id, db, CTX)
    db.refresh(account)
    db.refresh(rollup)
    db.refresh(cand)
    # account: PII and credentials gone
    assert account.name == TOMBSTONE
    assert account.email.startswith("erased-")
    assert account.password_hash is None
    assert account.email_verified is False
    # aggregate brief: quotes gone, structure tombstoned
    assert rollup.rollup == {"erased": True}
    assert rollup.consistency == []
    # candidacy itself tombstoned (pre-existing behavior still holds)
    assert cand.candidate_name == TOMBSTONE
