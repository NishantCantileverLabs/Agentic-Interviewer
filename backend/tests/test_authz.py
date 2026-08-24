"""Access-control contract tests — the production-posture gates, pinned.

These are the audit findings turned into CI: private reads reject anonymous
callers, candidate tokens stay scoped to their own session, session creation
is staff-only, and overrides demand a real rationale. If a refactor reopens
any of these, this file goes red.

Uses FastAPI's TestClient against the real app with dev_default_org forced
OFF, so "anonymous" here means what it means in production.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.tenancy import DEFAULT_ORG_ID, mint_candidate_token

DEV_ADMIN = {
    "X-Org-Id": str(DEFAULT_ORG_ID),
    "X-Role": "admin",
    "X-User-Email": "authz@test",
}


@pytest.fixture()
def client():
    settings = get_settings()
    original = settings.dev_default_org
    settings.dev_default_org = False  # production semantics for "anonymous"
    with TestClient(app) as c:
        yield c
    settings.dev_default_org = original


PRIVATE_READS = [
    "/sessions",
    "/candidacies",
    "/metrics/hiring",
    "/metrics/latency",
    "/metrics/llm-calls",
    "/calibration",
    "/review-queue",
    "/questions",
    "/role-configs",
    "/plans",
    "/job-roles",
]


@pytest.mark.parametrize("path", PRIVATE_READS)
def test_private_reads_reject_anonymous(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 403, f"{path} answered {resp.status_code} anonymously"


def test_session_results_reject_anonymous(client: TestClient) -> None:
    sid = uuid.uuid4()
    for path in (f"/sessions/{sid}/evaluation", f"/sessions/{sid}/brief",
                 f"/sessions/{sid}/brief.html", f"/sessions/{sid}/replay"):
        resp = client.get(path)
        assert resp.status_code == 403, f"{path} answered {resp.status_code} anonymously"


def test_session_create_rejects_anonymous(client: TestClient) -> None:
    resp = client.post("/sessions", json={"candidate_label": "authz-probe"})
    assert resp.status_code == 403


def test_candidate_token_is_session_scoped(client: TestClient) -> None:
    """A candidate link minted for session A must not read session B."""
    a = client.post("/sessions", headers=DEV_ADMIN, json={"candidate_label": "authz-a"})
    b = client.post("/sessions", headers=DEV_ADMIN, json={"candidate_label": "authz-b"})
    assert a.status_code == 201 and b.status_code == 201
    token, _ = mint_candidate_token(uuid.UUID(a.json()["id"]), DEFAULT_ORG_ID)
    other = b.json()["id"]
    for path in (f"/sessions/{other}/replay", f"/sessions/{other}/evaluation",
                 f"/sessions/{other}/brief.html"):
        resp = client.get(f"{path}?candidate_token={token}")
        assert resp.status_code == 403, f"{path} leaked across sessions ({resp.status_code})"


def test_candidate_token_reads_its_own_session(client: TestClient) -> None:
    a = client.post("/sessions", headers=DEV_ADMIN, json={"candidate_label": "authz-own"})
    sid = a.json()["id"]
    token, _ = mint_candidate_token(uuid.UUID(sid), DEFAULT_ORG_ID)
    resp = client.get(f"/sessions/{sid}/replay?candidate_token={token}")
    assert resp.status_code == 200


def test_override_requires_real_rationale(client: TestClient) -> None:
    """Invariant #10: a three-character rationale is not a rationale."""
    s = client.post("/sessions", headers=DEV_ADMIN, json={"candidate_label": "authz-r"})
    resp = client.post(
        f"/sessions/{s.json()['id']}/review-decision",
        headers=DEV_ADMIN,
        json={"inflow": "borderline", "decision": "override", "rationale": "n/a"},
    )
    assert resp.status_code == 422


def test_hiring_stats_reject_candidate_role(client: TestClient) -> None:
    """Candidate-scoped tokens rank below every staff gate."""
    s = client.post("/sessions", headers=DEV_ADMIN, json={"candidate_label": "authz-c"})
    token, _ = mint_candidate_token(uuid.UUID(s.json()["id"]), DEFAULT_ORG_ID)
    resp = client.get(f"/metrics/hiring?candidate_token={token}")
    assert resp.status_code == 403
