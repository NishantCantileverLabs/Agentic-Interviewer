"""T21 — case/consulting round plugin.

Pure logic: phase inference, exhibit-release validation, must-touch
redirects, math-block state. The conductor supplies live context (case pack,
transcript-derived coverage, time) through the ctx bag.
"""

from datetime import datetime
from typing import Any

from engine.round_registry import RoundTypeDef, register
from engine.state import EngineState

PHASES = ("CASE_INTRO", "CLARIFY", "STRUCTURE", "ANALYSIS", "BRAINSTORM", "SYNTHESIS")
# fraction of round budget at which each phase should begin (soft schedule;
# STRUCTURE→ANALYSIS additionally requires the structure_proposed intent)
PHASE_SCHEDULE = {
    "CASE_INTRO": 0.0,
    "CLARIFY": 0.06,
    "STRUCTURE": 0.15,
    "ANALYSIS": 0.35,
    "BRAINSTORM": 0.75,
    "SYNTHESIS": 0.85,
}
MUST_TOUCH_REDIRECT_REMAINING = 0.4  # redirect when must-touch untouched with <40% left


def current_phase(es: EngineState, round_id: str, elapsed_frac: float) -> str:
    """Deterministic phase: time schedule, gated on structure_proposed."""
    phase = "CASE_INTRO"
    for p in PHASES:
        if elapsed_frac >= PHASE_SCHEDULE[p]:
            phase = p
    # ANALYSIS and beyond require the candidate to have proposed a structure
    if phase in ("ANALYSIS", "BRAINSTORM") and not es.intent_seen(round_id, "structure_proposed"):
        return "STRUCTURE"
    return phase


def exhibit_release_allowed(
    pack: dict[str, Any], exhibit_id: str, es: EngineState, round_id: str
) -> bool:
    """Engine-owned release rules: 'on_request' exhibits release when the
    model requests them (it only requests after a qualifying candidate ask,
    per prompt); each releases at most once."""
    if f"{round_id}:{exhibit_id}" in es.exhibits_revealed:
        return False
    return any(e.get("id") == exhibit_id for e in pack.get("exhibits", []))


def untouched_must_areas(pack: dict[str, Any], transcript_text: str) -> list[str]:
    """Deterministic coverage check: a must_touch area counts as touched when
    any of its keywords appear in the conversation so far."""
    touched = transcript_text.lower()
    out = []
    for area in (pack.get("expected_structure") or {}).get("must_touch", []):
        keywords = [w for w in area.lower().split() if len(w) > 3]
        if not any(k in touched for k in keywords):
            out.append(area)
    return out


def active_math_block(
    pack: dict[str, Any], es: EngineState, round_id: str, phase: str
) -> dict[str, Any] | None:
    if phase != "ANALYSIS":
        return None
    for block in pack.get("math_blocks", []):
        if f"{round_id}:{block['id']}" not in es.math_correct:
            return block
    return None


def case_directive(
    es: EngineState,
    round_id: str,
    ctx: dict[str, Any],
    now: datetime | None = None,
) -> str | None:
    pack = ctx.get("case_pack")
    if not pack:
        return None
    elapsed_frac = float(ctx.get("elapsed_frac", 0.0))
    phase = current_phase(es, round_id, elapsed_frac)
    lines = [f"Case phase: {phase}."]

    if phase == "STRUCTURE" and not es.intent_seen(round_id, "structure_proposed"):
        lines.append(
            "The candidate must propose their own framework before analysis. When they "
            'lay one out, tag that turn intent "structure_proposed", ask "anything '
            'else?" exactly once, then probe the weakest branch. Never supply the framework.'
        )
    if phase == "ANALYSIS":
        block = active_math_block(pack, es, round_id, phase)
        if block:
            lines.append(
                f"Active math block {block['id']}: the reference answer is "
                f"{block['correct_value']} (±{block.get('tolerance_pct', 2)}%). Wait "
                "silently through calculation (thinking silence is normal). Confirm or "
                "correct ONLY their final number — the engine adjudicates it; if wrong, "
                "say so plainly and let them find the error once before helping. "
                f"Common traps: {', '.join(block.get('common_traps', [])) or 'none listed'}."
            )
        untouched = ctx.get("untouched_must_areas") or []
        if untouched and (1 - elapsed_frac) < MUST_TOUCH_REDIRECT_REMAINING:
            lines.append(
                f"Redirect now — untouched must-cover area: '{untouched[0]}'. Ask how "
                "they would think about it, conversationally."
            )
        lines.append(
            "Exhibits: release one only when the candidate's question genuinely calls "
            'for it — tag the turn intent "release_exhibit" with the exhibit id in '
            'competency field (e.g. {"intent":"release_exhibit","competency":"ex1"}).'
        )
    if phase == "SYNTHESIS" and not es.intent_seen(round_id, "synthesis_requested"):
        lines.append(
            'Open synthesis with the forcing move: "the client walks in — what do you '
            'tell them in 30 seconds?" Tag it intent "synthesis_requested". If they '
            "lead with caveats, ask for the recommendation first."
        )
    return "\n".join(lines)


register(
    RoundTypeDef(
        type="case",
        prompt_file="case_v1",
        tools=("scratchpad", "exhibits"),
        completion_intents=("structure_proposed", "synthesis_requested"),
        transition_hint=(
            "Open the case: read the client situation from the pack prompt "
            "conversationally, then invite clarifying questions."
        ),
        silence_maxhold_s=15,  # math-block thinking silence
        directive_extra=case_directive,
    )
)
