"""Seed the SQL question + a plan-driven rounds demo plan (becomes default).

    python scripts/seed_rounds.py [base_url]
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

SETUP_BASE = """
CREATE TABLE orders (id INTEGER, region TEXT, amount INTEGER, status TEXT);
INSERT INTO orders VALUES
 (1,'north',120,'paid'),(2,'south',80,'paid'),(3,'north',200,'refunded'),
 (4,'east',150,'paid'),(5,'south',70,'paid'),(6,'north',90,'paid');
"""

SETUP_H2 = """
CREATE TABLE orders (id INTEGER, region TEXT, amount INTEGER, status TEXT);
INSERT INTO orders VALUES
 (1,'west',500,'refunded'),(2,'west',10,'paid');
"""

SETUP_H3 = """
CREATE TABLE orders (id INTEGER, region TEXT, amount INTEGER, status TEXT);
"""

QUESTION_SQL = {
    "title": "Revenue by region",
    "statement_md": (
        "### Revenue by region (SQL)\n\n"
        "Table `orders(id, region, amount, status)`.\n\n"
        "Write one query returning each region's total **paid** revenue, ordered by "
        "total descending, then region ascending. Output columns: `region, total`.\n\n"
        "**Example** (for the sample data shown in visible test 1):\n"
        "```\nnorth|210\neast|150\nsouth|150\n```\n\n"
        "Regions with no paid orders must not appear."
    ),
    "language_targets": ["sql"],
    "visible_tests": {
        "cases": [
            {
                "id": "v1",
                "stdin": "",
                "setup_sql": SETUP_BASE,
                "expected_output": "north|210\neast|150\nsouth|150",
            }
        ]
    },
    "hidden_tests": {
        "cases": [
            {
                "id": "h1",
                "stdin": "",
                "setup_sql": SETUP_H2,
                "expected_output": "west|10",
            },
            {
                "id": "h2",
                "stdin": "",
                "setup_sql": SETUP_H3,
                "expected_output": "",
            },
        ]
    },
    "hints": {
        "levels": [
            "Ask which rows should even be counted before any grouping happens.",
            "Suggest filtering on status first, then thinking about GROUP BY.",
            "Point toward SUM(amount) with GROUP BY region, filtered WHERE status='paid', with ORDER BY.",
        ]
    },
    "twist": {
        "prompt": "Now also exclude any region whose paid total is below 100 — how does the query change?"
    },
    "difficulty": 2,
}


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=30, headers=DEV_AUTH) as c:
        questions = c.get("/questions").json()
        coding_q = next((q["id"] for q in questions if "Pair" in q["title"]), None)
        sql_q = next((q["id"] for q in questions if "Revenue" in q["title"]), None)
        if sql_q is None:
            resp = c.post("/questions", json=QUESTION_SQL)
            resp.raise_for_status()
            sql_q = resp.json()["id"]
            print(f"sql question: {sql_q}")
        else:
            print(f"sql question exists: {sql_q}")

        plans = c.get("/plans").json()
        rc_id = plans[0]["role_config_id"]
        plan = {
            "role_config_id": "sde_backend_rounds_demo",
            "rounds": [
                {"id": "intro", "type": "intro", "minutes": 1},
                {"id": "warmup", "type": "warmup", "minutes": 2},
                {"id": "coding", "type": "coding", "minutes": 4, "question": coding_q},
                {"id": "sql", "type": "sql", "minutes": 3, "question": sql_q},
                {"id": "wrapup", "type": "wrapup", "minutes": 1},
            ],
            "competencies": [
                {"id": "problem_solving", "weight": 0.3, "probe_budget": 3},
                {"id": "coding_proficiency", "weight": 0.3, "probe_budget": 3},
                {"id": "cs_fundamentals", "weight": 0.2, "probe_budget": 2},
                {"id": "communication", "weight": 0.2, "probe_budget": 2},
            ],
            "language_default": "python",
        }
        resp = c.post("/plans", json={"role_config_id": rc_id, "plan": plan})
        resp.raise_for_status()
        print(f"rounds demo plan: {resp.json()['id']} (~11 min traversal incl. SQL round)")
    print("\nSEEDED")


if __name__ == "__main__":
    main()
