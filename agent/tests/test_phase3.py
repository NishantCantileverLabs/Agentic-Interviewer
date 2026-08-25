"""Phase 3 acceptance-critical tests: T19 boundary/echo, T20 math fixtures,
T21 case gating, T22 canvas serialization, T23 design coverage, T24 STAR."""

import pathlib
from datetime import UTC, datetime, timedelta

from engine import ENDED, InterviewPlan, InterviewStateMachine, rebuild
from engine.canvas import labels, observation_block, serialize_scene
from engine.mathcheck import check_answer, extract_numbers
from engine.round_registry import RoundTypeDef, get_round_type, register, registered_types
from engine.rounds.behavioral import behavioral_directive, star_missing
from engine.rounds.case import (
    case_directive,
    current_phase,
    exhibit_release_allowed,
    untouched_must_areas,
)
from engine.rounds.design import component_coverage, design_directive

T0 = datetime(2026, 8, 23, 10, 0, 0, tzinfo=UTC)


def ev(seq, type_, payload=None, minutes=0.0):  # noqa: ANN001, ANN201
    return {"seq": seq, "type": type_, "payload": payload or {},
            "ts": T0 + timedelta(minutes=minutes)}


def turn(seq, intent, competency=None, minutes=0.0, extra=None):  # noqa: ANN001, ANN201
    payload = {"text": "...", "meta": {"intent": intent, "competency": competency}}
    payload.update(extra or {})
    return ev(seq, "agent_turn", payload, minutes)


# ── T19: boundary + dummy round ──────────────────────────────────────


def test_engine_never_imports_voice_path() -> None:
    """Invariant #15, mechanically enforced."""
    engine_dir = pathlib.Path(__file__).parent.parent / "engine"
    offenders = []
    for f in engine_dir.rglob("*.py"):
        src = f.read_text(encoding="utf-8")
        if "livekit" in src or "from pipeline" in src or "import pipeline" in src:
            offenders.append(f.name)
    assert not offenders, f"voice-path imports in engine: {offenders}"


def test_echo_round_registers_without_core_changes() -> None:
    assert "echo" in registered_types()
    register(RoundTypeDef(type="karaoke", prompt_file="warmup_v1"))
    assert get_round_type("karaoke").prompt_file == "warmup_v1"
    plan = InterviewPlan.from_json(
        {
            "role_config_id": "x",
            "rounds": [{"id": "k1", "type": "karaoke", "minutes": 1}],
            "competencies": [{"id": "communication", "weight": 1.0}],
        }
    )
    sm = InterviewStateMachine(plan)
    es = rebuild([ev(0, "state_transition", {"to": "k1"})], plan)
    assert sm.should_transition(es, T0 + timedelta(minutes=2)) == ENDED


# ── T20: number extraction fixtures (≥95% bar) ───────────────────────

MATH_FIXTURES = [
    ("the answer is 340 million", 340e6), ("about 340M", 340e6), ("0.34B", 0.34e9),
    ("roughly $2.5m per year", 2.5e6), ("it comes to 1,200,000", 1.2e6),
    ("I get three forty million", 340e6), ("three hundred forty million", 340e6),
    ("point three four billion", 0.34e9), ("34 crore", 34e7), ("2 lakh users", 2e5),
    ("about 1.5 crore", 1.5e7), ("50k QPS", 50e3), ("about twelve thousand", 12e3),
    ("€3.2bn", 3.2e9), ("₹500 crore", 500e7), ("call it 2 million", 2e6),
    ("maybe 750,000", 750e3), ("7.5 lakh", 7.5e5), ("a hundred million... no wait, 120 million",
        120e6),
    ("I'd estimate 45%", 45), ("twenty five thousand", 25e3), ("1.2 trillion", 1.2e12),
    ("4,50,000 in Indian format", 450e3), ("roughly 0.5m", 0.5e6),
    ("we're looking at 90 billion", 90e9), ("so 340", 340), ("total: 68,000", 68e3),
    ("six hundred thousand", 600e3), ("about 3.4 x 10... call it 34 million", 34e6),
    ("15 mn units", 15e6), ("2.75 bn", 2.75e9), ("just 900", 900),
    ("forty five million", 45e6), ("eighty crore", 80e7), ("1 lac", 1e5),
    ("5 thousand", 5e3), ("we get 12.5 million", 12.5e6), ("around 220k", 220e3),
    ("say 3 billion", 3e9), ("under 100 million", 100e6), ("1,000", 1000),
    ("two fifty million", 250e6), ("9.9 crore", 9.9e7), ("30 percent", 30),
    ("seventeen thousand", 17e3), ("0.75 billion", 0.75e9), ("660m", 660e6),
    ("call it 41,000", 41e3), ("just over 5 lakh", 5e5), ("88 bn", 88e9),
]


def test_number_extraction_fixture_suite() -> None:
    hits = 0
    misses = []
    for text, expected in MATH_FIXTURES:
        verdict = check_answer(text, expected, tolerance_pct=2)
        if verdict.correct:
            hits += 1
        else:
            misses.append((text, expected, verdict.stated))
    rate = hits / len(MATH_FIXTURES)
    assert rate >= 0.95, f"extraction rate {rate:.2%}; misses: {misses}"


def test_math_tolerance_and_wrong_answers() -> None:
    assert check_answer("340 million", 340e6, 2).correct
    assert check_answer("346 million", 340e6, 2).correct       # within 2%
    assert not check_answer("360 million", 340e6, 2).correct   # outside
    assert check_answer("no numbers here", 340e6).stated is None
    assert not extract_numbers("purely qualitative reasoning")


# ── T21: case round gating ───────────────────────────────────────────

PACK = {
    "prompt_md": "Client is a utility entering EV charging.",
    "clarifications": [],
    "exhibits": [
        {"id": "ex1", "title": "Market size", "type": "table", "content_md": "|seg|size|",
         "release": "on_request"},
    ],
    "expected_structure": {"must_touch": ["market size", "competition", "unit economics"]},
    "math_blocks": [
        {"id": "m1", "given": "x", "correct_value": 340000000, "tolerance_pct": 2,
         "common_traps": ["unit mismatch"]},
    ],
    "synthesis_expectation_md": "Recommendation with supports",
}

CASE_PLAN = InterviewPlan.from_json(
    {
        "role_config_id": "x",
        "rounds": [{"id": "case1", "type": "case", "minutes": 30, "case_pack": "cp-1"}],
        "competencies": [{"id": "problem_solving", "weight": 1.0}],
    }
)


def test_case_structure_gates_analysis() -> None:
    es = rebuild([ev(0, "state_transition", {"to": "case1"})], CASE_PLAN)
    # 50% through but no structure proposed -> stuck in STRUCTURE
    assert current_phase(es, "case1", 0.5) == "STRUCTURE"
    es2 = rebuild(
        [ev(0, "state_transition", {"to": "case1"}),
         turn(1, "structure_proposed", minutes=6)],
        CASE_PLAN,
    )
    assert current_phase(es2, "case1", 0.5) == "ANALYSIS"
    assert current_phase(es2, "case1", 0.9) == "SYNTHESIS"


def test_case_exhibit_release_engine_owned() -> None:
    es = rebuild([ev(0, "state_transition", {"to": "case1"})], CASE_PLAN)
    assert exhibit_release_allowed(PACK, "ex1", es, "case1")
    assert not exhibit_release_allowed(PACK, "nonexistent", es, "case1")
    es2 = rebuild(
        [ev(0, "state_transition", {"to": "case1"}),
         ev(1, "exhibit_revealed", {"round_id": "case1", "exhibit_id": "ex1"}, 5)],
        CASE_PLAN,
    )
    assert not exhibit_release_allowed(PACK, "ex1", es2, "case1")  # once only


def test_case_must_touch_redirect_and_math_directive() -> None:
    es = rebuild(
        [ev(0, "state_transition", {"to": "case1"}), turn(1, "structure_proposed", minutes=2)],
        CASE_PLAN,
    )
    transcript = "we sized the market at 300 million and discussed unit economics"
    untouched = untouched_must_areas(PACK, transcript)
    assert untouched == ["competition"]
    d = case_directive(
        es, "case1",
        {"case_pack": PACK, "elapsed_frac": 0.65, "untouched_must_areas": untouched},
    )
    assert "Redirect now" in d and "competition" in d
    assert "340000000" in d  # active math block adjudication reference
    # math answered correctly -> block no longer active
    es_done = rebuild(
        [ev(0, "state_transition", {"to": "case1"}),
         turn(1, "structure_proposed", minutes=2),
         turn(2, "chat", minutes=10, extra={"math_verdict": {"block_id": "m1", "correct": True}})],
        CASE_PLAN,
    )
    d2 = case_directive(es_done, "case1", {"case_pack": PACK, "elapsed_frac": 0.5})
    assert "340000000" not in (d2 or "")


# ── T22: canvas serialization ────────────────────────────────────────

SHAPES = [
    {"id": "n1", "kind": "box", "label": "API Gateway"},
    {"id": "n2", "kind": "box", "label": "Postgres"},
    {"id": "n3", "kind": "cylinder", "label": "S3"},
    {"id": "n4", "kind": "box", "label": ""},
    {"id": "a1", "kind": "arrow", "from": "n1", "to": "n2", "label": "writes"},
]


def test_canvas_serializer_scene_graph() -> None:
    scene = serialize_scene(SHAPES)
    assert len(scene["nodes"]) == 4 and len(scene["edges"]) == 1
    assert scene["unlabeled"] == 1
    assert scene["edges"][0] == {"from": "API Gateway", "to": "Postgres", "label": "writes"}
    block = observation_block(SHAPES, prev_shapes=SHAPES[:2])
    assert "@canvas_observation" in block and "API Gateway" in block
    assert "unlabeled_shapes: 1" in block
    assert "+ S3" in block  # diff picks up additions
    assert labels(SHAPES) == ["API Gateway", "Postgres", "S3"]


# ── T23: design round ────────────────────────────────────────────────

DESIGN_Q = {
    "requirement_sheet": {"users": "10M DAU"},
    "reference_components": ["API gateway", "Postgres database", "cache", "message queue"],
    "dive_areas": ["feed fanout"],
    "estimation_blocks": [{"id": "e1", "correct_value": 12000, "tolerance_pct": 5}],
}

DESIGN_PLAN = InterviewPlan.from_json(
    {
        "role_config_id": "x",
        "rounds": [{"id": "d1", "type": "system_design", "minutes": 40,
                    "design_question": "dq-1"}],
        "competencies": [{"id": "problem_solving", "weight": 1.0}],
    }
)


def test_design_requirements_gate_and_coverage() -> None:
    from engine.rounds.design import current_phase as design_phase

    es = rebuild([ev(0, "state_transition", {"to": "d1"})], DESIGN_PLAN)
    assert design_phase(es, "d1", 0.5) == "REQUIREMENTS"  # gated
    es2 = rebuild(
        [ev(0, "state_transition", {"to": "d1"}), turn(1, "requirements_stated", minutes=3)],
        DESIGN_PLAN,
    )
    assert design_phase(es2, "d1", 0.6) == "DEEP_DIVE"

    cov = component_coverage(
        DESIGN_Q["reference_components"], ["api gateway", "postgres", "redis cache"]
    )
    assert cov["coverage"] == 0.75 and cov["missing"] == ["message queue"]

    d = design_directive(
        es2, "d1",
        {"design_question": DESIGN_Q, "elapsed_frac": 0.6, "component_coverage": cov},
    )
    assert "feed fanout" in d  # dive fires at >=60% coverage
    d2 = design_directive(es2, "d1", {"design_question": DESIGN_Q, "elapsed_frac": 0.85})
    assert "scale_question" in d2 and "failure_question" in d2


def test_design_wrapup_blocked_until_scale_and_failure() -> None:
    sm = InterviewStateMachine(DESIGN_PLAN)
    es = rebuild(
        [ev(0, "state_transition", {"to": "d1"}), turn(1, "requirements_stated", minutes=1)],
        DESIGN_PLAN,
    )
    assert not sm.round_complete(es, DESIGN_PLAN.round_by_id("d1"))
    es2 = rebuild(
        [ev(0, "state_transition", {"to": "d1"}),
         turn(1, "requirements_stated", minutes=1),
         turn(2, "scale_question", minutes=30),
         turn(3, "failure_question", minutes=32)],
        DESIGN_PLAN,
    )
    assert sm.round_complete(es2, DESIGN_PLAN.round_by_id("d1"))


# ── T24: behavioral STAR mechanics ───────────────────────────────────

BEHAV_PLAN = InterviewPlan.from_json(
    {
        "role_config_id": "x",
        "rounds": [{"id": "b1", "type": "behavioral", "minutes": 20}],
        "competencies": [{"id": "communication", "weight": 1.0}],
    }
)


def test_star_steering_and_contradiction_once() -> None:
    es = rebuild(
        [ev(0, "state_transition", {"to": "b1"}),
         turn(1, "star_S", minutes=2), turn(2, "star_T", minutes=3)],
        BEHAV_PLAN,
    )
    assert star_missing(es, "b1") == ["A", "R"]
    d = behavioral_directive(
        es, "b1",
        {"unprobed_claims": ["reduced infra cost 30%"],
         "contradictions": ["overlap between role X and role Y"]},
    )
    assert "Action" in d and "THEY specifically" in d
    assert "reduced infra cost 30%" in d
    assert "clarify_contradiction" in d
    # after the clarification was asked once, it never re-queues
    es2 = rebuild(
        [ev(0, "state_transition", {"to": "b1"}),
         turn(1, "clarify_contradiction", minutes=4)],
        BEHAV_PLAN,
    )
    d2 = behavioral_directive(
        es2, "b1", {"contradictions": ["overlap between role X and role Y"]}
    )
    assert "clarify_contradiction" not in (d2 or "")
