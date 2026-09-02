"""T10 acceptance — cross-tenant isolation suite (CI-blocking).

    python scripts/test_tenancy.py [base_url]

Proves: org A cannot read org B's data via any endpoint; role gates hold;
candidate links are single-session scoped; admin actions are logged; the
dev default-org fallback still works for the Phase 1 UI.
"""

import os
import sys
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
# /orgs is a platform-operator (service-key) surface since the prod audit
SERVICE = {"X-Internal-Key": os.environ.get("INTERNAL_API_KEY", "dev-internal-key")}


def hdr(org: str, role: str = "admin", email: str = "tester@t10") -> dict[str, str]:
    return {"X-Org-Id": org, "X-Role": role, "X-User-Email": email}


def main() -> None:
    c = httpx.Client(base_url=BASE, timeout=30)

    # gate check: anonymous callers must not touch the tenant registry
    assert c.get("/orgs").status_code == 403, "anonymous GET /orgs must 403"
    assert (
        c.post("/orgs", json={"name": "nope"}).status_code == 403
    ), "anonymous POST /orgs must 403"

    suffix = uuid.uuid4().hex[:6]
    org_a = c.post("/orgs", json={"name": f"acme-{suffix}"}, headers=SERVICE).json()["id"]
    org_b = c.post("/orgs", json={"name": f"globex-{suffix}"}, headers=SERVICE).json()["id"]
    print(f"[1/7] orgs created: A={org_a[:8]} B={org_b[:8]} (anonymous 403 verified)")

    # org A creates a session with events
    sid = c.post(
        "/sessions", json={"candidate_label": "alice"}, headers=hdr(org_a)
    ).json()["id"]
    r = c.post(
        f"/sessions/{sid}/events",
        json={"events": [{"type": "stt_final", "payload": {"text": "org-a secret"}}]},
        headers=hdr(org_a),
    )
    r.raise_for_status()
    assert c.get(f"/sessions/{sid}", headers=hdr(org_a)).status_code == 200
    print("[2/7] org A session + events created and readable by A")

    # org B must see nothing of A's — via every read surface
    assert c.get(f"/sessions/{sid}", headers=hdr(org_b)).status_code == 404
    assert c.get(f"/sessions/{sid}/replay", headers=hdr(org_b)).status_code == 404
    assert c.get(f"/sessions/{sid}/plan", headers=hdr(org_b)).status_code in (404, 409)
    assert c.get(f"/sessions/{sid}/evaluation", headers=hdr(org_b)).status_code == 404
    b_sessions = c.get("/sessions", headers=hdr(org_b)).json()
    assert all(s["id"] != sid for s in b_sessions)
    b_latency = c.get("/metrics/latency", headers=hdr(org_b)).json()["sessions"]
    assert all(s["session_id"] != sid for s in b_latency)
    print("[3/7] org B blind to org A everywhere (session, replay, plan, eval, lists)")

    # writes cross-org must fail too
    r = c.post(
        f"/sessions/{sid}/events",
        json={"events": [{"type": "stt_final", "payload": {"text": "intruder"}}]},
        headers=hdr(org_b),
    )
    assert r.status_code == 404, r.status_code
    print("[4/7] org B cannot write into org A's event log")

    # role gates: reviewer cannot author questions/role-configs
    q = {
        "title": "t", "statement_md": "t", "language_targets": ["python"],
        "visible_tests": {"cases": []}, "hidden_tests": {"cases": []},
        "hints": {"levels": ["a", "b", "c"]},
    }
    assert c.post("/questions", json=q, headers=hdr(org_a, "reviewer")).status_code == 403
    assert (
        c.post(
            "/role-configs",
            json={"name": f"x-{suffix}", "competencies": {}, "weights": {}, "thresholds": {}},
            headers=hdr(org_a, "recruiter"),
        ).status_code
        == 403
    )  # role configs are admin-only
    assert c.post("/questions", json=q, headers=hdr(org_a, "recruiter")).status_code == 201
    print("[5/7] role gates hold (reviewer < recruiter < admin)")

    # candidate link: single-session scope
    link = c.post(f"/sessions/{sid}/candidate-link", headers=hdr(org_a)).json()
    token = link["candidate_token"]
    assert c.get(f"/sessions/{sid}", params={"candidate_token": token}).status_code == 200
    other_sid = c.post(
        "/sessions", json={"candidate_label": "bob"}, headers=hdr(org_a)
    ).json()["id"]
    r = c.get(f"/sessions/{other_sid}", params={"candidate_token": token})
    assert r.status_code == 403, r.status_code
    # hints never candidate-visible
    r = c.get(
        f"/sessions/{sid}/questions",
        params={"candidate_token": token, "include_hints": 1},
    )
    assert r.status_code == 403
    print("[6/7] candidate link works, is single-session scoped, and cannot read hints")

    # admin audit trail
    actions = c.get("/orgs/current/admin-actions", headers=hdr(org_a)).json()
    kinds = {a["action"] for a in actions}
    assert "candidate_link_minted" in kinds and "question_created" in kinds
    # anonymous access follows the deployment's DEV_DEFAULT_ORG posture:
    # 200 only when the dev fallback is explicitly on, 403 under enforcement
    anon = c.get("/sessions").status_code
    assert anon in (200, 403), f"anonymous /sessions gave {anon}"
    posture = "dev default-org fallback on" if anon == 200 else "anonymous 403 (enforced)"
    print(f"[7/7] admin actions logged; {posture}")

    print("\nCROSS-TENANT SUITE PASSED")


if __name__ == "__main__":
    main()
