"""Contract tests for the interviewer-voice pick (PATCH /sessions/{id}/voice).

The lobby sets it with a session-scoped candidate token; the agent reads it
back from the session GET at bootstrap. Unknown voices are rejected — the
value is passed to Deepgram as a model name, so only the whitelist may pass.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes.sessions import INTERVIEWER_VOICES
from app.tenancy import DEFAULT_ORG_ID

DEV_RECRUITER = {
    "X-Org-Id": str(DEFAULT_ORG_ID),
    "X-Role": "recruiter",
    "X-User-Email": "voice@test",
}


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _make_session(client: TestClient) -> str:
    resp = client.post(
        "/sessions", json={"candidate_label": "voice-test"}, headers=DEV_RECRUITER
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_voice_set_and_read_back(client: TestClient) -> None:
    sid = _make_session(client)
    resp = client.patch(
        f"/sessions/{sid}/voice",
        json={"voice": "aura-2-orion-en"},
        headers=DEV_RECRUITER,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["voice"] == "aura-2-orion-en"
    # the agent reads the session GET at bootstrap — voice must be in it
    got = client.get(f"/sessions/{sid}", headers=DEV_RECRUITER)
    assert got.json()["voice"] == "aura-2-orion-en"


def test_voice_rejects_unknown_model(client: TestClient) -> None:
    sid = _make_session(client)
    resp = client.patch(
        f"/sessions/{sid}/voice",
        json={"voice": "aura-2-evil-injection"},
        headers=DEV_RECRUITER,
    )
    assert resp.status_code == 422


def test_voice_settable_with_candidate_token(client: TestClient) -> None:
    """The lobby holds only the candidate token — that must be enough."""
    sid = _make_session(client)
    resp = client.post(f"/sessions/{sid}/candidate-link", headers=DEV_RECRUITER)
    token = resp.json()["candidate_token"]
    resp = client.patch(
        f"/sessions/{sid}/voice?candidate_token={token}",
        json={"voice": "aura-2-andromeda-en"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["voice"] == "aura-2-andromeda-en"


def test_candidate_token_cannot_set_other_sessions_voice(client: TestClient) -> None:
    sid_a = _make_session(client)
    sid_b = _make_session(client)
    token = client.post(
        f"/sessions/{sid_a}/candidate-link", headers=DEV_RECRUITER
    ).json()["candidate_token"]
    resp = client.patch(
        f"/sessions/{sid_b}/voice?candidate_token={token}",
        json={"voice": "aura-2-thalia-en"},
    )
    assert resp.status_code == 403


def test_whitelist_matches_frontend_contract(client: TestClient) -> None:
    """Every whitelisted voice must actually be settable."""
    sid = _make_session(client)
    for v in INTERVIEWER_VOICES:
        resp = client.patch(
            f"/sessions/{sid}/voice", json={"voice": v}, headers=DEV_RECRUITER
        )
        assert resp.status_code == 200, f"{v}: {resp.text}"
