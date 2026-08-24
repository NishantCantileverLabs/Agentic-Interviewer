"""Engine unit tests: rounds, rebuild purity, transitions, budgets, meta."""

from datetime import UTC, datetime, timedelta

from engine import ENDED, InterviewPlan, InterviewStateMachine, parse_meta, rebuild

PLAN = InterviewPlan.from_json(
    {
        "role_config_id": "sde_backend_v1",
        "rounds": [
            {"id": "intro", "type": "intro", "minutes": 2},
            {"id": "warmup", "type": "warmup", "minutes": 5},
            {"id": "coding", "type": "coding", "minutes": 22, "question": "q-1"},
            {"id": "sql", "type": "sql", "minutes": 10, "question": "q-2"},
            {"id": "wrapup", "type": "wrapup", "minutes": 4},
        ],
        "competencies": [
            {"id": "problem_solving", "weight": 0.4, "probe_budget": 3},
            {"id": "cs_fundamentals", "weight": 0.3, "probe_budget": 2},
            {"id": "communication", "weight": 0.3, "probe_budget": 2},
        ],
    }
)

LEGACY_PLAN = InterviewPlan.from_json(
    {
        "role_config_id": "sde_backend_v1",
        "time_budget_min": {"INTRO": 2, "WARMUP": 5, "TECHNICAL_DEEPDIVE": 12, "CODING": 22, "WRAPUP": 4},
        "competencies": [{"id": "problem_solving", "weight": 1.0, "probe_budget": 3}],
        "question_refs": {"coding": "q-legacy"},
    }
)

T0 = datetime(2026, 8, 23, 10, 0, 0, tzinfo=UTC)


def ev(seq: int, type_: str, payload: dict | None = None, minutes: float = 0) -> dict:
    return {"seq": seq, "type": type_, "payload": payload or {}, "ts": T0 + timedelta(minutes=minutes)}


def agent_turn(seq: int, intent: str, competency: str | None = None, minutes: float = 0) -> dict:
    return ev(seq, "agent_turn", {"text": "...", "meta": {"intent": intent, "competency": competency}}, minutes)


def test_legacy_plan_synthesizes_classic_rounds() -> None:
    assert [r.id for r in LEGACY_PLAN.rounds] == [
        "INTRO", "WARMUP", "TECHNICAL_DEEPDIVE", "CODING", "WRAPUP",
    ]
    coding = LEGACY_PLAN.round_by_id("CODING")
    assert coding is not None and coding.question_id == "q-legacy" and coding.minutes == 22


def test_rebuild_is_pure_and_deterministic() -> None:
    events = [
        ev(0, "state_transition", {"to": "intro"}),
        ev(1, "stt_final", {"text": "hi"}, 0.5),
        agent_turn(2, "probe", "problem_solving", 1),
        ev(3, "state_transition", {"to": "warmup"}, 2),
        ev(4, "hint_issued", {"level": 1}, 3),
    ]
    a = rebuild(events, PLAN)
    b = rebuild(list(events), PLAN)
    assert a == b
    assert a.round_id == "warmup"
    assert a.probes_used == {"problem_solving": 1}
    assert [(rid, lvl) for rid, lvl, _ in a.hint_history] == [("warmup", 1)]
    assert a.candidate_turns == 1 and a.agent_turns == 1


def test_transition_walks_plan_rounds_in_order() -> None:
    sm = InterviewStateMachine(PLAN)
    es = rebuild([ev(0, "state_transition", {"to": "intro"})], PLAN)
    assert sm.should_transition(es, T0 + timedelta(minutes=1)) is None
    assert sm.should_transition(es, T0 + timedelta(minutes=2, seconds=1)) == "warmup"
    # sql round follows coding
    es_sql = rebuild([ev(0, "state_transition", {"to": "coding"})], PLAN)
    assert sm.should_transition(es_sql, T0 + timedelta(minutes=23)) == "sql"
    # last round -> ENDED
    es_end = rebuild([ev(0, "state_transition", {"to": "wrapup"})], PLAN)
    assert sm.should_transition(es_end, T0 + timedelta(minutes=5)) == ENDED


def test_code_round_completion_criteria_per_round() -> None:
    sm = InterviewStateMachine(PLAN)
    events = [
        ev(0, "state_transition", {"to": "coding"}),
        agent_turn(1, "complexity_question", minutes=10),
        agent_turn(2, "testing_question", minutes=11),
        ev(3, "state_transition", {"to": "sql"}, 22),
    ]
    es = rebuild(events, PLAN)
    coding = PLAN.round_by_id("coding")
    sql = PLAN.round_by_id("sql")
    assert sm.round_complete(es, coding)  # criteria met in coding round
    assert not sm.round_complete(es, sql)  # sql round has its own criteria
    directive = sm.directive(es, T0 + timedelta(minutes=30))
    assert "complexity" in directive  # steering resumes for the sql round


def test_probe_budget_exhaustion_directive() -> None:
    sm = InterviewStateMachine(PLAN)
    events = [ev(0, "state_transition", {"to": "warmup"})]
    events += [agent_turn(i + 1, "probe", "cs_fundamentals", minutes=i + 1) for i in range(2)]
    es = rebuild(events, PLAN)
    assert es.probes_remaining(PLAN)["cs_fundamentals"] == 0
    directive = sm.directive(es, T0 + timedelta(minutes=5))
    assert "cs_fundamentals" in directive and "move on" in directive


def test_parse_meta_happy_and_malformed() -> None:
    meta, text = parse_meta(
        '@meta{"intent":"probe","competency":"problem_solving","hint_level":null}\nWhat breaks at scale?'
    )
    assert meta.intent == "probe" and text == "What breaks at scale?"
    meta2, text2 = parse_meta("@meta{not json}\nStill spoken.")
    assert meta2.intent == "chat" and text2 == "Still spoken."


def test_parse_meta_scrubs_inline_headers() -> None:
    # header mid-text (model misbehavior seen live) must never reach speech
    meta, text = parse_meta(
        'Nice work. @meta{"intent":"hint","competency":null,"hint_level":2} '
        "Think about what you have already seen."
    )
    assert meta.intent == "hint" and meta.hint_level == 2
    assert "@meta" not in text
    assert text == "Nice work. Think about what you have already seen."


def test_hint_escalation_gating() -> None:
    sm = InterviewStateMachine(PLAN)
    now = T0 + timedelta(minutes=5)
    es = rebuild([ev(0, "state_transition", {"to": "coding"})], PLAN)
    # no hints yet -> level 1 authorized
    assert sm.authorized_hint_level(es, now, tests_failing=True) == 1
    # level 1 issued 30s ago -> locked (90s gap not elapsed)
    es2 = rebuild(
        [ev(0, "state_transition", {"to": "coding"}),
         ev(1, "hint_issued", {"round_id": "coding", "level": 1}, minutes=4.5)],
        PLAN,
    )
    assert sm.authorized_hint_level(es2, now, tests_failing=True) is None
    # level 1 issued 3 min ago + still failing -> level 2
    es3 = rebuild(
        [ev(0, "state_transition", {"to": "coding"}),
         ev(1, "hint_issued", {"round_id": "coding", "level": 1}, minutes=2)],
        PLAN,
    )
    assert sm.authorized_hint_level(es3, now, tests_failing=True) == 2
    # tests passing -> no escalation
    assert sm.authorized_hint_level(es3, now, tests_failing=False) is None
    # level 3 already issued -> exhausted
    es4 = rebuild(
        [ev(0, "state_transition", {"to": "coding"}),
         ev(1, "hint_issued", {"round_id": "coding", "level": 3}, minutes=1)],
        PLAN,
    )
    assert sm.authorized_hint_level(es4, now, tests_failing=True) is None


def test_twist_fires_only_with_budget_remaining() -> None:
    sm = InterviewStateMachine(PLAN)  # coding round = 22 min
    es = rebuild([ev(0, "state_transition", {"to": "coding"})], PLAN)
    early = T0 + timedelta(minutes=5)   # ~77% remaining
    late = T0 + timedelta(minutes=18)   # ~18% remaining
    assert sm.should_fire_twist(es, early, visible_tests_passed=True, has_twist=True)
    assert not sm.should_fire_twist(es, late, visible_tests_passed=True, has_twist=True)
    assert not sm.should_fire_twist(es, early, visible_tests_passed=False, has_twist=True)
    # already fired for this round -> never again
    es_fired = rebuild(
        [ev(0, "state_transition", {"to": "coding"}),
         ev(1, "twist_injected", {"round_id": "coding"}, minutes=4)],
        PLAN,
    )
    assert not sm.should_fire_twist(es_fired, early, visible_tests_passed=True, has_twist=True)


def test_nudge_max_twice_and_requires_silence() -> None:
    sm = InterviewStateMachine(PLAN)
    base = [
        ev(0, "state_transition", {"to": "coding"}),
        ev(1, "stt_final", {"text": "starting now"}, 1),
    ]
    es = rebuild(base, PLAN)
    # 2 minutes of silent editing -> nudge
    assert sm.should_nudge(es, T0 + timedelta(minutes=3), editing=True)
    # spoke recently -> no nudge
    assert not sm.should_nudge(es, T0 + timedelta(minutes=1, seconds=30), editing=True)
    # not editing -> no nudge (thinking silence is tolerated)
    assert not sm.should_nudge(es, T0 + timedelta(minutes=3), editing=False)
    # two nudges already used in this round -> capped
    nudged = base + [
        ev(2, "agent_turn", {"text": "walk me through?", "meta": {"intent": "chat"}, "nudge": True}, 4),
        ev(3, "agent_turn", {"text": "thinking out loud helps", "meta": {"intent": "chat"}, "nudge": True}, 7),
    ]
    es2 = rebuild(nudged, PLAN)
    assert not sm.should_nudge(es2, T0 + timedelta(minutes=10), editing=True)


def test_crash_recovery_midway_equals_full_rebuild() -> None:
    from engine.state import apply_event

    events = [
        ev(0, "state_transition", {"to": "intro"}),
        ev(1, "state_transition", {"to": "warmup"}, 2),
        agent_turn(2, "probe", "communication", 3),
        ev(3, "state_transition", {"to": "coding"}, 7),
        agent_turn(4, "complexity_question", minutes=8),
        ev(5, "twist_injected", {}, 9),
    ]
    full = rebuild(events, PLAN)
    partial = rebuild(events[:4], PLAN)
    for e in events[4:]:
        partial = apply_event(partial, e["type"], e["payload"], e["ts"])
    assert partial == full
