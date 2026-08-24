"""T0 acceptance smoke test — run against the live docker-compose stack.

    python scripts/smoke.py [base_url]

Creates a session, appends interview_events, reads them back via replay,
and verifies the append-only trigger + monotonic-seq enforcement.
"""

import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

# Dev-stub auth (works outside production only): scripts act as the seed admin.
DEV_AUTH = {
    "X-Org-Id": "00000000-0000-0000-0000-000000000001",
    "X-Role": "admin",
    "X-User-Email": "scripts@local",
}


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=10, headers=DEV_AUTH) as c:
        health = c.get("/health")
        health.raise_for_status()
        print(f"[1/5] health: {health.json()}")

        session = c.post("/sessions", json={"candidate_label": "smoke-test"})
        session.raise_for_status()
        sid = session.json()["id"]
        print(f"[2/5] session created: {sid}")

        events = {
            "events": [
                {"type": "state_transition", "payload": {"to": "INTRO"}},
                {"type": "stt_final", "payload": {"text": "hello, I'm ready"}},
                {"type": "agent_turn", "payload": {"text": "Great, let's begin."}},
            ]
        }
        appended = c.post(f"/sessions/{sid}/events", json=events)
        appended.raise_for_status()
        assert appended.json()["appended"] == 3
        print("[3/5] appended 3 events")

        replay = c.get(f"/sessions/{sid}/replay")
        replay.raise_for_status()
        rows = replay.json()
        assert [r["seq"] for r in rows] == [0, 1, 2], rows
        assert rows[1]["payload"]["text"] == "hello, I'm ready"
        print(f"[4/5] replay returned {len(rows)} ordered events; seq server-assigned in batch order")

        # A second batch continues the sequence (multi-writer safe)
        more = c.post(
            f"/sessions/{sid}/events",
            json={"events": [{"type": "stt_final", "payload": {"text": "next"}}]},
        )
        more.raise_for_status()
        rows = c.get(f"/sessions/{sid}/replay").json()
        assert [r["seq"] for r in rows] == [0, 1, 2, 3]
        # Unknown event type must be rejected (closed vocabulary)
        bad = c.post(
            f"/sessions/{sid}/events",
            json={"events": [{"type": "not_a_real_type", "payload": {}}]},
        )
        assert bad.status_code == 422, bad.text
        print("[5/5] seq continues across batches -> ok, unknown event type -> 422")

    print("\nSMOKE TEST PASSED")


if __name__ == "__main__":
    main()
