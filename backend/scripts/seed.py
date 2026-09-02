"""Seed dev data: role config, coding questions, and an interview plan.

    python scripts/seed.py [base_url]

Idempotent-ish: skips seeding when a plan already exists.
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

ROLE_CONFIG = {
    "name": "sde_backend_v1",
    "competencies": {
        "problem_solving": "Decomposes problems, reasons about trade-offs",
        "coding_proficiency": "Writes working, clean code under time pressure",
        "cs_fundamentals": "Data structures, complexity, systems basics",
        "communication": "Explains clearly, thinks aloud, listens",
    },
    "weights": {
        "problem_solving": 0.3,
        "coding_proficiency": 0.3,
        "cs_fundamentals": 0.2,
        "communication": 0.2,
    },
    "thresholds": {"strong_hire": 4.4, "hire": 3.6, "no_hire": 2.6},
}

QUESTION_PAIR_SUM = {
    "title": "Pair with target sum",
    "statement_md": (
        "### Pair with target sum\n\n"
        "Read two lines from stdin: line 1 is a space-separated list of integers, "
        "line 2 is a target integer.\n\n"
        "Print `YES` if any **two distinct** elements sum to the target, else `NO`.\n\n"
        "**Example**\n```\ninput:  2 7 11 15\n        9\noutput: YES\n```\n\n"
        "Aim for better than O(n²)."
    ),
    "language_targets": ["python", "javascript", "java", "cpp"],
    "visible_tests": {
        "cases": [
            {"id": "v1", "stdin": "2 7 11 15\n9", "expected_output": "YES"},
            {"id": "v2", "stdin": "1 2 3 4\n100", "expected_output": "NO"},
        ]
    },
    "hidden_tests": {
        "cases": [
            {"id": "h1", "stdin": "5\n10", "expected_output": "NO"},          # single element
            {"id": "h2", "stdin": "5 5\n10", "expected_output": "YES"},        # duplicates allowed
            {"id": "h3", "stdin": "-3 1 8\n5", "expected_output": "YES"},      # negatives
            {"id": "h4", "stdin": "0 0\n1", "expected_output": "NO"},
        ]
    },
    "hints": {
        "levels": [
            "Ask what the cost of checking every pair is, and whether they can trade memory for time.",
            "Suggest thinking about what you'd need to have already seen to complete a pair in one pass.",
            "Point toward a hash set of seen values: for each x, check whether target minus x was seen.",
        ]
    },
    "twist": {
        "prompt": "Now the input list is a stream too large for memory — can your approach adapt, and what changes?",
    },
    "difficulty": 2,
}


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=30, headers=DEV_AUTH) as c:
        if c.get("/plans").json():
            print("plans already exist — skipping seed")
            return
        rc = c.post("/role-configs", json=ROLE_CONFIG)
        rc.raise_for_status()
        rc_id = rc.json()["id"]
        print(f"role config: {rc_id}")

        q = c.post("/questions", json=QUESTION_PAIR_SUM)
        q.raise_for_status()
        q_id = q.json()["id"]
        print(f"question: {q_id} ({QUESTION_PAIR_SUM['title']})")

        plan = c.post(
            "/plans",
            json={
                "role_config_id": rc_id,
                "plan": {
                    "role_config_id": "sde_backend_v1",
                    "time_budget_min": {
                        "INTRO": 2,
                        "WARMUP": 5,
                        "TECHNICAL_DEEPDIVE": 12,
                        "CODING": 22,
                        "WRAPUP": 4,
                    },
                    "competencies": [
                        {"id": "problem_solving", "weight": 0.3, "probe_budget": 3},
                        {"id": "coding_proficiency", "weight": 0.3, "probe_budget": 3},
                        {"id": "cs_fundamentals", "weight": 0.2, "probe_budget": 2},
                        {"id": "communication", "weight": 0.2, "probe_budget": 2},
                    ],
                    "question_refs": {"coding": q_id},
                    "language_default": "python",
                },
            },
        )
        plan.raise_for_status()
        print(f"plan: {plan.json()['id']}")
    print("\nSEEDED")


if __name__ == "__main__":
    main()
