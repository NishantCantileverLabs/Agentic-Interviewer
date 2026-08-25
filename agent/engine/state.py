"""Interview engine state machine — plan-driven rounds.

Invariant #6: engine state is a pure function of the event log —
`rebuild(events, plan)` folds the ordered event stream into an EngineState
with no hidden inputs. The state machine owns transitions; the LLM is only
informed of them via directives.

`EngineState.round_id` holds the current round's id (a plan-defined string;
legacy logs use the classic state names). `ENDED` is the virtual terminal.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from engine.plan import ENDED, InterviewPlan, Round


@dataclass(frozen=True)
class EngineState:
    round_id: str | None = None  # None until the first state_transition event
    round_entered_ts: datetime | None = None
    session_started_ts: datetime | None = None
    probes_used: dict[str, int] = field(default_factory=dict)
    # (round_id, level, ts) per hint issued — drives graduated escalation
    hint_history: tuple[tuple[str, int, datetime], ...] = ()
    twists_fired: frozenset[str] = frozenset()
    # per-round intent coverage: frozenset of "round_id:intent" markers.
    # Registry completion_intents check against this (T19 generalization of
    # the old complexity/testing flags).
    intents_seen: frozenset[str] = frozenset()
    # exhibits revealed per round ("round_id:exhibit_id")
    exhibits_revealed: frozenset[str] = frozenset()
    # math blocks answered correctly ("round_id:block_id")
    math_correct: frozenset[str] = frozenset()
    # think-aloud nudges per round (max 2) + last candidate speech time
    nudges: dict[str, int] = field(default_factory=dict)
    last_candidate_ts: datetime | None = None
    candidate_turns: int = 0
    agent_turns: int = 0

    def hints_in_round(self, round_id: str) -> list[tuple[int, datetime]]:
        return [(lvl, ts) for rid, lvl, ts in self.hint_history if rid == round_id]

    def probes_remaining(self, plan: InterviewPlan) -> dict[str, int]:
        return {
            c.id: max(0, c.probe_budget - self.probes_used.get(c.id, 0))
            for c in plan.competencies
        }

    def intent_seen(self, round_id: str, intent: str) -> bool:
        return f"{round_id}:{intent}" in self.intents_seen

    # Back-compat views over the generalized intent tracking
    @property
    def complexity_discussed(self) -> frozenset[str]:
        return frozenset(
            m.split(":", 1)[0] for m in self.intents_seen if m.endswith(":complexity_question")
        )

    @property
    def testing_question_asked(self) -> frozenset[str]:
        return frozenset(
            m.split(":", 1)[0] for m in self.intents_seen if m.endswith(":testing_question")
        )


def apply_event(es: EngineState, type_: str, payload: dict[str, Any], ts: datetime) -> EngineState:
    """Fold one event into the engine state. Pure."""
    if es.session_started_ts is None:
        es = replace(es, session_started_ts=ts)

    if type_ == "state_transition":
        return replace(es, round_id=str(payload["to"]), round_entered_ts=ts)

    if type_ == "stt_final":
        return replace(es, candidate_turns=es.candidate_turns + 1, last_candidate_ts=ts)

    if type_ == "agent_turn":
        es = replace(es, agent_turns=es.agent_turns + 1)
        meta = payload.get("meta") or {}
        intent = meta.get("intent", "chat")
        rid = es.round_id or ""
        if intent == "probe" and meta.get("competency"):
            comp = str(meta["competency"])
            probes = dict(es.probes_used)
            probes[comp] = probes.get(comp, 0) + 1
            es = replace(es, probes_used=probes)
        if intent not in ("chat", "probe"):
            es = replace(es, intents_seen=es.intents_seen | {f"{rid}:{intent}"})
        if payload.get("nudge"):
            nudges = dict(es.nudges)
            nudges[rid] = nudges.get(rid, 0) + 1
            es = replace(es, nudges=nudges)
        verdict = payload.get("math_verdict")
        if verdict and verdict.get("correct"):
            marker = f"{rid}:{verdict.get('block_id', '?')}"
            es = replace(es, math_correct=es.math_correct | {marker})
        return es

    if type_ == "exhibit_revealed":
        rid = str(payload.get("round_id") or es.round_id or "")
        marker = f"{rid}:{payload.get('exhibit_id', '?')}"
        return replace(es, exhibits_revealed=es.exhibits_revealed | {marker})

    if type_ == "hint_issued":
        rid = str(payload.get("round_id") or es.round_id or "")
        entry = (rid, int(payload["level"]), ts)
        return replace(es, hint_history=(*es.hint_history, entry))

    if type_ == "twist_injected":
        rid = str(payload.get("round_id") or es.round_id or "")
        return replace(es, twists_fired=es.twists_fired | {rid})

    return es


def rebuild(events: list[dict[str, Any]], plan: InterviewPlan) -> EngineState:  # noqa: ARG001
    """Rebuild engine state from an ordered event stream (crash recovery)."""
    es = EngineState()
    for ev in events:
        ts = ev["ts"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        es = apply_event(es, ev["type"], ev.get("payload") or {}, ts)
    return es


class InterviewStateMachine:
    """Transition evaluation + per-turn directives. Holds no state of its own —
    callers pass the current EngineState (rebuilt or incrementally folded)."""

    def __init__(self, plan: InterviewPlan) -> None:
        self.plan = plan

    def current_round(self, es: EngineState) -> Round | None:
        if es.round_id is None or es.round_id == ENDED:
            return None
        return self.plan.round_by_id(es.round_id)

    def time_in_round_s(self, es: EngineState, now: datetime) -> float:
        if es.round_entered_ts is None:
            return 0.0
        return (now - es.round_entered_ts).total_seconds()

    def round_complete(self, es: EngineState, round_: Round) -> bool:
        """Registry-driven completion criteria (T19): a round is clean-complete
        when every completion intent has been seen in it."""
        from engine.round_registry import completion_intents_for

        required = completion_intents_for(round_.type)
        return all(es.intent_seen(round_.id, intent) for intent in required)

    def should_transition(self, es: EngineState, now: datetime) -> str | None:
        """Returns the next round id (or ENDED), engine-evaluated only."""
        if es.round_id == ENDED:
            return None
        round_ = self.current_round(es)
        if round_ is None:
            return self.plan.first_round().id
        budget_spent = self.time_in_round_s(es, now) >= round_.minutes * 60
        if not budget_spent:
            return None
        # Code rounds hold until completion criteria OR full budget expiry —
        # budget expiry forces the move regardless (time is the hard limit).
        nxt = self.plan.next_round(round_.id)
        return nxt.id if nxt else ENDED

    HINT_ESCALATION_GAP_S = 90.0
    TWIST_MIN_BUDGET_REMAINING = 0.4
    NUDGE_SILENCE_S = 90.0
    MAX_NUDGES_PER_ROUND = 2

    def authorized_hint_level(
        self, es: EngineState, now: datetime, tests_failing: bool
    ) -> int | None:
        """Graduated hints (§7.3): level N+1 unlocks only after level N was
        issued ≥90s prior AND tests still fail. Returns the next level (1-3)
        the engine authorizes, or None when escalation is exhausted/locked."""
        rid = es.round_id or ""
        issued = es.hints_in_round(rid)
        if not issued:
            return 1
        last_level, last_ts = issued[-1]
        if last_level >= 3:
            return None
        if not tests_failing:
            return None
        if (now - last_ts).total_seconds() < self.HINT_ESCALATION_GAP_S:
            return None
        return last_level + 1

    def should_fire_twist(
        self, es: EngineState, now: datetime, visible_tests_passed: bool, has_twist: bool
    ) -> bool:
        """Twist fires when the base solution passes visible tests with ≥40%
        of the round budget remaining (§7.3)."""
        round_ = self.current_round(es)
        if round_ is None or not has_twist or not visible_tests_passed:
            return False
        if round_.id in es.twists_fired:
            return False
        remaining = 1 - self.time_in_round_s(es, now) / (round_.minutes * 60)
        return remaining >= self.TWIST_MIN_BUDGET_REMAINING

    def should_nudge(self, es: EngineState, now: datetime, editing: bool) -> bool:
        """Think-aloud nudge: candidate coding silently >90s, max 2 per round."""
        rid = es.round_id or ""
        if es.nudges.get(rid, 0) >= self.MAX_NUDGES_PER_ROUND:
            return False
        if not editing or es.last_candidate_ts is None:
            return False
        return (now - es.last_candidate_ts).total_seconds() >= self.NUDGE_SILENCE_S

    def directive(self, es: EngineState, now: datetime) -> str:
        """Round directive for the uncached context tail (block D)."""
        round_ = self.current_round(es)
        if round_ is None:
            return "The interview has ended. Say goodbye warmly."
        remaining = es.probes_remaining(self.plan)
        lines = [
            f"You are in the '{round_.id}' round (type: {round_.type}).",
            "Probe budget remaining: "
            + ", ".join(f"{cid}={n}" for cid, n in remaining.items()),
        ]
        exhausted = [cid for cid, n in remaining.items() if n == 0]
        if exhausted:
            lines.append(
                "Budget exhausted for: "
                + ", ".join(exhausted)
                + ". Do not probe these further — acknowledge and move on."
            )
        if not self.round_complete(es, round_):
            from engine.round_registry import completion_intents_for

            missing = [
                f'cover the "{intent}" step (tag it with that intent)'
                for intent in completion_intents_for(round_.type)
                if not es.intent_seen(round_.id, intent)
            ]
            if missing and self.time_in_round_s(es, now) > 0.7 * round_.minutes * 60:
                lines.append("Before this round can end you must: " + "; ".join(missing))
        return "\n".join(lines)
