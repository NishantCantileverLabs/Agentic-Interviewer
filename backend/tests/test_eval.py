"""T6/T7 unit tests: deterministic signals, validation, hire-signal math."""

import pytest

from app.eval.brief import build_summary, hire_signal
from app.eval.pipeline import (
    EvidenceItem,
    _parse_json_object,
    _validate_scores,
    build_transcript,
)
from app.eval.signals import compute_signals

EVENTS = [
    {"id": 1, "seq": 0, "ts": "2026-08-23T10:00:00+00:00", "type": "state_transition",
     "payload": {"to": "intro", "round_type": "intro"}},
    {"id": 2, "seq": 1, "ts": "2026-08-23T10:01:00+00:00", "type": "stt_final",
     "payload": {"text": "I built a RAG pipeline with reranking"}},
    {"id": 3, "seq": 2, "ts": "2026-08-23T10:01:05+00:00", "type": "agent_turn",
     "payload": {"text": "How did you measure it?", "meta": {"intent": "probe"}}},
    {"id": 4, "seq": 3, "ts": "2026-08-23T10:02:00+00:00", "type": "state_transition",
     "payload": {"to": "coding", "round_type": "coding"}},
    {"id": 5, "seq": 4, "ts": "2026-08-23T10:02:30+00:00", "type": "editor_delta_batch",
     "payload": {"deltas": []}},
    {"id": 6, "seq": 5, "ts": "2026-08-23T10:03:00+00:00", "type": "paste",
     "payload": {"length": 300}},
    {"id": 7, "seq": 6, "ts": "2026-08-23T10:04:00+00:00", "type": "run_clicked",
     "payload": {}},
    {"id": 8, "seq": 7, "ts": "2026-08-23T10:05:00+00:00", "type": "run_clicked",
     "payload": {}},
    {"id": 9, "seq": 8, "ts": "2026-08-23T10:05:02+00:00", "type": "execution_result",
     "payload": {"language": "python",
                 "response": {"status": "accepted",
                              "per_test": [{"passed": True}, {"passed": True}]}}},
    {"id": 10, "seq": 9, "ts": "2026-08-23T10:06:00+00:00", "type": "hint_issued",
     "payload": {"level": 1}},
    {"id": 11, "seq": 10, "ts": "2026-08-23T10:07:00+00:00", "type": "tab_visibility",
     "payload": {"visible": False}},
]


def test_signals_deterministic_and_correct() -> None:
    s = compute_signals(EVENTS)
    assert s["hints_used"] == 1 and s["hint_levels"] == [1]
    assert s["paste_count"] == 1
    assert s["flagged_pastes"] == [{"event_id": 6, "length": 300}]  # >120 flagged
    assert s["tab_switches_away"] == 1
    assert s["run_count"] == 2 and s["run_gap_seconds"] == [60.0]
    assert s["time_to_first_line_s"] == 30.0  # coding entry 10:02 -> first delta 10:02:30
    assert s["final_execution_status"] == "accepted"
    assert compute_signals(EVENTS) == s  # deterministic


def test_transcript_numbers_lines_with_event_ids() -> None:
    t = build_transcript(EVENTS)
    assert "[2] CANDIDATE: I built a RAG pipeline" in t
    assert "[3] INTERVIEWER (probe):" in t
    assert "[9] EVENT: code run (python) -> accepted, 2/2 tests passed" in t


def test_score_validation_rejects_unresolvable_refs() -> None:
    evidence = {"problem_solving": [EvidenceItem(event_id=2, quote="x", why_relevant="y")]}
    good = {"problem_solving": {"score_1_to_5": 4, "confidence": 0.8,
                                "evidence_refs": [2], "rationale": "ok"}}
    out = _validate_scores(good, evidence, ["problem_solving"])
    assert out["problem_solving"].score_1_to_5 == 4

    bad_refs = {"problem_solving": {"score_1_to_5": 4, "confidence": 0.8,
                                    "evidence_refs": [999], "rationale": "ok"}}
    with pytest.raises(ValueError, match="no resolvable evidence"):
        _validate_scores(bad_refs, evidence, ["problem_solving"])


def test_json_parsing_tolerates_fences() -> None:
    assert _parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_json_object('Here you go: {"a": 1}') == {"a": 1}


COMPETENCIES = [
    {"id": "a", "weight": 0.5},
    {"id": "b", "weight": 0.3},
    {"id": "c", "weight": 0.2},
]


def _rubric(sa: int, sb: int, sc: int) -> dict:
    def comp(score: int) -> dict:
        return {
            "score_1_to_5": score, "confidence": 0.9, "evidence_refs": [1],
            "rationale": "r",
            "evidence": [{"event_id": 1, "quote": "q", "why_relevant": "w"}],
        }
    return {"competencies": {"a": comp(sa), "b": comp(sb), "c": comp(sc)}, "degraded": False}


def test_hire_signal_thresholds() -> None:
    t = {"strong_hire": 4.4, "hire": 3.6, "no_hire": 2.6}
    assert hire_signal(4.5, t) == "strong hire"
    assert hire_signal(4.0, t) == "hire"
    assert hire_signal(3.0, t) == "no hire"
    assert hire_signal(2.0, t) == "strong no hire"


def test_summary_weighted_score_and_signal_changes_with_weights() -> None:
    thresholds = {"strong_hire": 4.4, "hire": 3.6, "no_hire": 2.6}
    rubric = _rubric(5, 2, 2)
    s1 = build_summary(rubric, {"flagged_pastes": []}, COMPETENCIES, thresholds)
    # 5*0.5 + 2*0.3 + 2*0.2 = 3.5 -> no hire
    assert s1["recruiter"]["weighted_score"] == 3.5
    assert s1["recruiter"]["signal"] == "no hire"

    # Re-weighting toward competency 'a' flips the outcome (T7 acceptance)
    reweighted = [{"id": "a", "weight": 0.9}, {"id": "b", "weight": 0.05}, {"id": "c", "weight": 0.05}]
    s2 = build_summary(rubric, {"flagged_pastes": []}, reweighted, thresholds)
    assert s2["recruiter"]["weighted_score"] == 4.7
    assert s2["recruiter"]["signal"] == "strong hire"


def test_summary_claims_all_carry_citations() -> None:
    s = build_summary(_rubric(5, 4, 2), {"flagged_pastes": []}, COMPETENCIES,
                      {"strong_hire": 4.4, "hire": 3.6, "no_hire": 2.6})
    for claim in s["recruiter"]["strengths"] + s["recruiter"]["risks"]:
        assert claim["citation"] is not None
        assert claim["citation"]["event_id"] == 1
