"""Phase 3 backend units: T27 roll-up math (hand-computed), invariant #17
citation validation, T24 resume parsing + contradictions, trajectory."""

from app.eval.aggregate import (
    rollup_competencies,
    trajectory,
    validate_consistency_claims,
)
from app.rounds.resume_parser import find_contradictions, parse_resume

R1 = {
    "round_index": 0, "round_type": "behavioral",
    "rubric": {"competencies": {
        "communication": {"score_1_to_5": 4, "confidence": 0.8,
                          "evidence": [{"event_id": 11, "quote": "a"}]},
        "problem_solving": {"score_1_to_5": 3, "confidence": 0.6, "evidence": []},
    }},
}
R2 = {
    "round_index": 1, "round_type": "coding",
    "rubric": {"competencies": {
        "communication": {"score_1_to_5": 2, "confidence": 0.7,
                          "evidence": [{"event_id": 22, "quote": "b"}]},
        "coding_proficiency": {"score_1_to_5": 5, "confidence": 0.9, "evidence": []},
    }},
}


def test_rollup_weighted_merge_hand_computed() -> None:
    # weights: behavioral 1.0, coding 2.0
    out = rollup_competencies([R1, R2], [1.0, 2.0])
    # communication: (4*1 + 2*2) / 3 = 8/3 = 2.67
    assert out["communication"]["score"] == 2.67
    assert out["communication"]["observations"] == 2
    assert out["communication"]["confidence_band"] == "medium"
    # single-observation competencies -> low confidence
    assert out["coding_proficiency"]["score"] == 5.0
    assert out["coding_proficiency"]["confidence_band"] == "low"
    # merged evidence carries round attribution
    rounds_cited = {e["round_index"] for e in out["communication"]["evidence"]}
    assert rounds_cited == {0, 1}


def test_trajectory_labels() -> None:
    up = trajectory([
        {"rubric": {"competencies": {"a": {"score_1_to_5": 2}}}},
        {"rubric": {"competencies": {"a": {"score_1_to_5": 4}}}},
    ])
    assert up["label"] == "improving"
    down = trajectory([
        {"rubric": {"competencies": {"a": {"score_1_to_5": 4}}}},
        {"rubric": {"competencies": {"a": {"score_1_to_5": 3}}}},
    ])
    assert down["label"] == "declining" and down["fatigue_note"]
    assert trajectory([R1])["label"] == "single_round"


def test_consistency_claims_require_citations_in_every_session() -> None:
    """Invariant #17 — uncited or partially-cited claims are dropped."""
    valid = {"s1": {1, 2, 3}, "s2": {10, 11}}
    claims = [
        {"kind": "consistent", "statement": "ok",
         "citations": {"s1": [2], "s2": [10]}},          # valid
        {"kind": "tension", "statement": "one-sided",
         "citations": {"s1": [1]}},                       # only one session
        {"kind": "tension", "statement": "bad ids",
         "citations": {"s1": [99], "s2": [10]}},          # unresolvable id
        {"kind": "consistent", "statement": "uncited", "citations": {}},
    ]
    out = validate_consistency_claims(claims, valid)
    assert len(out) == 1 and out[0]["statement"] == "ok"


RESUME = """
Senior Data Scientist, Acme — Jan 2021 - Present
- Reduced infra cost 30% by rearchitecting the feature store
Data Scientist, Globex — 2018 - 2020
- Improved model AUC from 0.71 to 0.83 across 4 products
Consultant, Initech — 2019 - 2022
Analyst, Umbrella — 2019 - 2021
"""


def test_resume_parser_claims_and_roles() -> None:
    parsed = parse_resume(RESUME)
    assert parsed["parser_version"]
    assert len(parsed["roles"]) == 4
    assert parsed["roles"][0]["end_year"] == 9999  # present
    assert any("30%" in c for c in parsed["quantified_claims"])
    assert any("0.83" in c for c in parsed["quantified_claims"])


def test_resume_contradictions_deterministic() -> None:
    parsed = parse_resume(RESUME)
    cons = find_contradictions(parsed)
    assert cons, "3 concurrent roles should raise one neutral question"
    assert len(cons) <= 2
    # impossible range
    bad = parse_resume("Engineer, X — 2022 - 2019")
    assert any("ends before it starts" in c for c in find_contradictions(bad))
    # parser never raises on garbage
    assert parse_resume("\x00\x01 garbage \xff")["parser_version"]
