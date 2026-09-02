"""T4 acceptance smoke test — run with the sandbox profile up.

    python scripts/smoke_exec.py [base_url]

Exercises correct / infinite-loop / OOM / network-egress submissions and a
visible+hidden test suite, asserting hidden expected outputs never appear.
"""

import sys
import time
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

# Dev-stub auth (works outside production only): scripts act as the seed admin.
DEV_AUTH = {
    "X-Org-Id": "00000000-0000-0000-0000-000000000001",
    "X-Role": "admin",
    "X-User-Email": "scripts@local",
}
HIDDEN_SECRET = "hidden-secret-777"


def seed_question() -> str:
    """Insert a test question directly (question CRUD lands later)."""
    import sqlalchemy as sa

    sys.path.insert(0, ".")
    from app.config import get_settings

    engine = sa.create_engine(
        get_settings().database_url.replace("@postgres:", "@localhost:")
    )
    qid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO questions
                  (id, org_id, title, statement_md, language_targets, visible_tests,
                   hidden_tests, hints, twist, difficulty)
                VALUES
                  (:id, :org, 'Sum two ints', 'Read two ints, print their sum.',
                   ARRAY['python'],
                   CAST(:visible AS jsonb), CAST(:hidden AS jsonb),
                   CAST(:hints AS jsonb), NULL, 1)
                """
            ),
            {
                "id": qid,
                "org": "00000000-0000-0000-0000-000000000001",
                "visible": '{"cases": [{"id": "v1", "stdin": "1 2", "expected_output": "3"}]}',
                "hidden": '{"cases": [{"id": "h1", "stdin": "40 2", "expected_output": "42"},'
                ' {"id": "h2", "stdin": "0 0", "expected_output": "' + HIDDEN_SECRET + '"}]}',
                "hints": '{"levels": ["nudge", "direction", "partial"]}',
            },
        )
    return qid


def run(c: httpx.Client, sid: str, source: str, **kwargs: object) -> dict:
    resp = c.post(
        "/execute",
        json={"session_id": sid, "language": "python", "source": source, **kwargs},
    )
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=60, headers=DEV_AUTH) as c:
        sid = c.post("/sessions", json={"candidate_label": "t4-exec-smoke"}).json()["id"]

        t0 = time.monotonic()
        ok = run(c, sid, "print('hello')")
        assert ok["status"] == "accepted" and ok["stdout"].strip() == "hello", ok
        print(f"[1/6] correct run: accepted in {time.monotonic() - t0:.1f}s")

        t0 = time.monotonic()
        tle = run(c, sid, "while True:\n    pass")
        assert tle["status"] == "time_limit_exceeded", tle
        print(f"[2/6] infinite loop: {tle['status']} in {time.monotonic() - t0:.1f}s")

        t0 = time.monotonic()
        oom = run(c, sid, "x = [0] * (10**9)\nprint(len(x))")
        assert oom["status"] in ("memory_limit_exceeded", "runtime_error"), oom
        print(f"[3/6] OOM: {oom['status']} in {time.monotonic() - t0:.1f}s")

        net = run(
            c,
            sid,
            "import urllib.request\n"
            "print(urllib.request.urlopen('http://example.com', timeout=5).status)",
        )
        assert net["status"] != "accepted", net
        print(f"[4/6] network egress blocked: {net['status']}")

        qid = seed_question()
        suite = run(
            c,
            sid,
            "a, b = map(int, input().split())\nprint(a + b)",
            test_suite_id=qid,
        )
        assert suite["status"] == "failed", suite  # h2 expects the secret, sum prints 0
        by_id = {t["id"]: t for t in suite["per_test"]}
        assert by_id["v1"]["passed"] and by_id["h1"]["passed"] and not by_id["h2"]["passed"]
        body = str(suite)
        assert HIDDEN_SECRET not in body and "expected_output" not in body
        assert "stdout" not in by_id["h1"], by_id["h1"]
        print("[5/6] suite run: visible detail present, hidden cases pass/fail only")

        events = c.get(f"/sessions/{sid}/replay").json()
        exec_events = [e for e in events if e["type"] == "execution_result"]
        assert len(exec_events) == 5, len(exec_events)
        print(f"[6/6] {len(exec_events)} execution_result events in the log")

    print("\nT4 SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
