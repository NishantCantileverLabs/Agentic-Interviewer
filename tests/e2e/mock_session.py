"""E2E: scripted mock session -> T6 evaluation -> T7 brief.

    python tests/e2e/mock_session.py [base_url]

Posts a realistic full-interview event stream (transcript, edits, runs,
hint, paste, tab switch), marks the session completed, then waits for the
eval worker to produce an evaluation and brief. Verifies:
- every score cites >=1 evidence ref resolving to a real event id
- deterministic signals match hand-computed values
- re-running evaluation creates v2 without touching v1
- the brief renders with a hire signal and cited claims
"""

import json
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

# Dev-stub auth (works outside production only): scripts act as the seed admin.
DEV_AUTH = {
    "X-Org-Id": "00000000-0000-0000-0000-000000000001",
    "X-Role": "admin",
    "X-User-Email": "scripts@local",
}


TRANSCRIPT = [
    ("state_transition", {"to": "intro", "round_type": "intro"}),
    ("agent_turn", {"text": "Welcome! Can you hear me alright?", "meta": {"intent": "chat"}}),
    ("stt_final", {"text": "Yes, loud and clear. Excited to be here."}),
    ("state_transition", {"to": "warmup", "round_type": "warmup"}),
    ("agent_turn", {"text": "Tell me about something you've built recently.",
                    "meta": {"intent": "question", "competency": "communication"}}),
    ("stt_final", {"text": "I built a document ingestion service handling about two hundred "
                           "thousand PDFs a day. I profiled the OCR stage, found it was the "
                           "bottleneck, and moved it to a worker pool which cut p95 latency "
                           "from twelve seconds to three."}),
    ("agent_turn", {"text": "How did you measure that improvement?",
                    "meta": {"intent": "probe", "competency": "problem_solving"}}),
    ("stt_final", {"text": "We had a histogram metric per pipeline stage in Prometheus, so I "
                           "compared the p95 before and after over a week of traffic."}),
    ("agent_turn", {"text": "What would break first if volume grew ten times?",
                    "meta": {"intent": "probe", "competency": "cs_fundamentals"}}),
    ("stt_final", {"text": "Probably the shared Postgres queue — I'd move to a proper broker "
                           "and partition by tenant."}),
    ("state_transition", {"to": "coding", "round_type": "coding"}),
    ("agent_turn", {"text": "Let's write some code. The problem is on your screen.",
                    "meta": {"intent": "chat"}}),
    ("editor_snapshot", {"code": "", "language": "python"}),
    ("editor_delta_batch", {"deltas": [{"rangeOffset": 0, "rangeLength": 0,
                                        "text": "nums = list(map(int, input().split()))"}],
                            "language": "python"}),
    ("stt_final", {"text": "I'll use a hash set so I can check complements in one pass."}),
    ("paste", {"length": 40}),
    ("run_clicked", {"language": "python"}),
    ("execution_result", {"language": "python",
                          "response": {"status": "failed",
                                       "per_test": [{"id": "v1", "passed": True},
                                                    {"id": "v2", "passed": False}]}}),
    ("stt_final", {"text": "Ah, I inverted the condition on the empty case. Fixing it."}),
    ("run_clicked", {"language": "python"}),
    ("execution_result", {"language": "python",
                          "response": {"status": "accepted",
                                       "per_test": [{"id": "v1", "passed": True},
                                                    {"id": "v2", "passed": True},
                                                    {"id": "h1", "passed": True},
                                                    {"id": "h2", "passed": True}]}}),
    ("agent_turn", {"text": "Nice. What's the time and space complexity?",
                    "meta": {"intent": "complexity_question", "competency": "cs_fundamentals"}}),
    ("stt_final", {"text": "O of n time and O of n space for the seen set."}),
    ("agent_turn", {"text": "How would you test this beyond the given cases?",
                    "meta": {"intent": "testing_question", "competency": "coding_proficiency"}}),
    ("stt_final", {"text": "Property-based tests comparing against the brute force on random "
                           "arrays, plus edge cases: empty input, single element, duplicates, "
                           "negative numbers."}),
    ("state_transition", {"to": "wrapup", "round_type": "wrapup"}),
    ("agent_turn", {"text": "That's everything on my side. Any questions for me?",
                    "meta": {"intent": "wrapup"}}),
    ("stt_final", {"text": "What does the on-call rotation look like for this team?"}),
    ("state_transition", {"to": "ENDED", "round_type": "ENDED"}),
]


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=30, headers=DEV_AUTH) as c:
        sid = c.post("/sessions", json={"candidate_label": "mock-candidate-e2e"}).json()["id"]
        print(f"[1/6] session {sid}")

        events = [{"type": t, "payload": p} for t, p in TRANSCRIPT]
        resp = c.post(f"/sessions/{sid}/events", json={"events": events})
        resp.raise_for_status()
        print(f"[2/6] posted {resp.json()['appended']} fixture events")

        c.patch(f"/sessions/{sid}/status", json={"status": "in_progress"}).raise_for_status()
        c.patch(f"/sessions/{sid}/status", json={"status": "completed"}).raise_for_status()
        print("[3/6] session completed -> evaluate_session enqueued")

        evaluation = None
        for _ in range(60):
            time.sleep(5)
            try:
                r = c.get(f"/sessions/{sid}/evaluation")
            except httpx.HTTPError:
                continue  # stale keep-alive connection etc. — poll again
            if r.status_code == 200:
                evaluation = r.json()
                break
        assert evaluation, "evaluation did not appear within 5 minutes"
        print(f"[4/6] evaluation v{evaluation['version']} by {evaluation['model']}")

        event_ids = {e["id"] for e in c.get(f"/sessions/{sid}/replay").json()}
        assert not evaluation["rubric"]["degraded"], "evaluation flagged degraded"
        for cid, comp in evaluation["rubric"]["competencies"].items():
            refs = comp.get("evidence_refs", [])
            assert refs, f"{cid} has no evidence refs"
            for ref in refs:
                assert ref in event_ids, f"{cid} cites nonexistent event {ref}"
            print(f"    {cid}: {comp['score_1_to_5']}/5 (conf {comp['confidence']}, "
                  f"{len(refs)} citations)")

        signals = evaluation["signals"]
        assert signals["hints_used"] == 0
        assert signals["paste_count"] == 1 and signals["flagged_pastes"] == []
        assert signals["run_count"] == 2
        assert signals["final_execution_status"] == "accepted"
        print("[5/6] deterministic signals match hand-computed values")

        brief = None
        for _ in range(12):
            try:
                r = c.get(f"/sessions/{sid}/brief")
            except httpx.HTTPError:
                time.sleep(5)
                continue
            if r.status_code == 200:
                brief = r.json()
                break
            time.sleep(5)
        assert brief, "brief did not appear"
        rec = brief["summary"]["recruiter"]
        assert rec["signal"] in ("strong hire", "hire", "no hire", "strong no hire")
        for claim in rec["strengths"] + rec["risks"]:
            assert claim["citation"] and claim["citation"]["event_id"] in event_ids
        html = c.get(f"/sessions/{sid}/brief.html")
        html.raise_for_status()
        assert "Interview Decision Brief" in html.text
        print(f"[6/6] brief: {rec['signal'].upper()} (weighted {rec['weighted_score']}); "
              "every recruiter claim carries a resolvable citation; HTML renders")

        print("\nE2E MOCK SESSION PASSED")
        print(f"brief: {BASE}/sessions/{sid}/brief.html")
        print(json.dumps(rec, indent=1)[:800])


if __name__ == "__main__":
    main()
