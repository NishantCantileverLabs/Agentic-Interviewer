"""Seed Phase 3 fixtures: one authored case pack, one design question, and a
3-round pipeline (behavioral -> case -> system design).

    python scripts/seed_phase3.py [base_url]
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

CASE_PACK = {
    "title": "EV charging market entry",
    "pack": {
        "case_id": "market_entry_ev_charging_v1",
        "prompt_md": (
            "Our client is a large German utility. They are considering entering the "
            "public EV fast-charging market in Germany and want to know: should they, "
            "and how?"
        ),
        "clarifications": [
            {"trigger_topics": ["geography", "scope"], "answer_md": "Focus on Germany only."},
            {"trigger_topics": ["timeline"], "answer_md": "Board decision horizon is 5 years."},
        ],
        "exhibits": [
            {"id": "ex1", "title": "German EV fleet forecast", "type": "table",
             "content_md": "| year | EVs on road |\n|---|---|\n| 2026 | 3.4M |\n| 2030 | 10.2M |",
             "release": "on_request"},
            {"id": "ex2", "title": "Competitor fast-charging pricing", "type": "table",
             "content_md": "| operator | €/kWh |\n|---|---|\n| Ionity | 0.79 |\n| EnBW | 0.61 |\n| Tesla (open) | 0.52 |",
             "release": "on_request"},
        ],
        "expected_structure": {
            "acceptable_frames": [
                "market attractiveness / ability to win / economics",
                "market, competition, capabilities, entry mode",
            ],
            "must_touch": ["market size", "competition", "unit economics", "entry mode"],
        },
        "math_blocks": [
            {"id": "m1",
             "given": "10M EVs by 2030, 20% rely on public fast charging, 1,700 kWh/yr each at €0.60/kWh",
             "correct_value": 2040000000, "tolerance_pct": 3,
             "common_traps": ["forgetting the 20% public-charging share", "kWh vs MWh units"]},
        ],
        "brainstorm_prompts": ["What could make this market unattractive in 5 years?"],
        "synthesis_expectation_md": "Clear go/no-go with 2-3 supports and key risks.",
    },
}

DESIGN_QUESTION = {
    "title": "Design a URL shortener at scale",
    "requirement_sheet": {
        "functional": "shorten, redirect, custom aliases, expiry",
        "non_functional": "100M new links/month, 10B redirects/month, p99 redirect < 100ms",
    },
    "reference_components": [
        "API gateway / load balancer", "application service", "key generation service",
        "database", "cache", "analytics pipeline",
    ],
    "dive_areas": ["key generation collisions and pre-allocation", "cache invalidation on expiry"],
    "estimation_blocks": [
        {"id": "e1", "given": "10B redirects/month -> average QPS",
         "correct_value": 3900, "tolerance_pct": 10},
    ],
}


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=30, headers=DEV_AUTH) as c:
        packs = c.get("/case-packs").json()
        if not any(p["title"] == CASE_PACK["title"] for p in packs):
            r = c.post("/case-packs", json=CASE_PACK)
            r.raise_for_status()
            print(f"case pack: {r.json()['id']}")
        dqs = c.get("/design-questions").json()
        if not any(q["title"] == DESIGN_QUESTION["title"] for q in dqs):
            r = c.post("/design-questions", json=DESIGN_QUESTION)
            r.raise_for_status()
            print(f"design question: {r.json()['id']}")

        pack_id = next(p["id"] for p in c.get("/case-packs").json()
                       if p["title"] == CASE_PACK["title"])
        dq_id = next(q["id"] for q in c.get("/design-questions").json()
                     if q["title"] == DESIGN_QUESTION["title"])

        pipelines = c.get("/pipelines").json()
        if not any(p["name"] == "SDE full loop" for p in pipelines):
            r = c.post("/pipelines", json={
                "name": "SDE full loop",
                "rounds": [
                    {"round_type": "behavioral", "duration_min": 8, "sitting": 1,
                     "gate": "none", "weight": 1.0},
                    {"round_type": "case", "duration_min": 12, "sitting": 1,
                     "gate": "none", "weight": 1.5, "case_pack": pack_id},
                    {"round_type": "system_design", "duration_min": 12, "sitting": 2,
                     "gate": "review", "weight": 1.5, "design_question": dq_id},
                ],
            })
            r.raise_for_status()
            print(f"pipeline: {r.json()['id']}")
    print("PHASE 3 SEEDED")


if __name__ == "__main__":
    main()
