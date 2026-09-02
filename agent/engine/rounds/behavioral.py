"""T24 — behavioral round plugin.

STAR tracking rides the @meta channel (the conduct model reports which STAR
components the current story covers via intents star_S/star_T/star_A/star_R);
the directive steers to the missing component. Resume claims and detected
contradictions arrive via ctx (parsed deterministically backend-side).
"""

from typing import Any

from engine.round_registry import RoundTypeDef, register
from engine.state import EngineState

STAR = ("S", "T", "A", "R")
STAR_LABELS = {
    "S": "Situation (context, stakes)",
    "T": "Task (what needed to happen)",
    "A": "Action (what THEY specifically did — not the team)",
    "R": "Result (outcome, ideally quantified)",
}


def star_missing(es: EngineState, round_id: str) -> list[str]:
    return [c for c in STAR if not es.intent_seen(round_id, f"star_{c}")]


def behavioral_directive(es: EngineState, round_id: str, ctx: dict[str, Any]) -> str | None:
    lines = []
    missing = star_missing(es, round_id)
    if missing:
        nxt = missing[0]
        lines.append(
            f"Current story STAR coverage — missing: {', '.join(missing)}. Steer to "
            f"{STAR_LABELS[nxt]}. When a component gets covered, tag that turn intent "
            f'"star_{nxt}". If the Action stays collective ("we did"), ask what they '
            "personally did."
        )
    else:
        lines.append(
            "Story complete (full STAR). Move to the next competency story or probe "
            "the result's numbers."
        )
    claims = ctx.get("unprobed_claims") or []
    if claims:
        c = claims[0]
        lines.append(
            f"Unprobed resume claim: \"{c}\". Verify it like a technical claim — "
            "what was the baseline, how was it measured. Tag intent \"probe\"."
        )
    contradictions = ctx.get("contradictions") or []
    for con in contradictions[:1]:
        if not es.intent_seen(round_id, "clarify_contradiction"):
            lines.append(
                f"One neutral clarification (never confrontation), tagged intent "
                f'"clarify_contradiction": "help me understand the timeline — {con}"'
            )
    return "\n".join(lines) if lines else None


register(
    RoundTypeDef(
        type="behavioral",
        prompt_file="behavioral_v1",
        tools=(),
        completion_intents=("star_S", "star_T", "star_A", "star_R"),
        transition_hint=(
            "Move into behavioral territory: ask for a specific story from their "
            "actual experience (use the resume)."
        ),
        silence_maxhold_s=8,
        directive_extra=behavioral_directive,
    )
)
