"""T23 — system design round plugin.

Phases mirror the case round's deterministic scheduling; requirements-first
nudge, estimation via the shared math checker, dive-area trigger on component
coverage, mandatory scale+failure completion intents.
"""

from typing import Any

from engine.round_registry import RoundTypeDef, register
from engine.state import EngineState

PHASES = ("REQUIREMENTS", "ESTIMATION", "HIGH_LEVEL_DESIGN", "DEEP_DIVE", "SCALE_AND_FAILURE")
PHASE_SCHEDULE = {
    "REQUIREMENTS": 0.0,
    "ESTIMATION": 0.15,
    "HIGH_LEVEL_DESIGN": 0.3,
    "DEEP_DIVE": 0.55,
    "SCALE_AND_FAILURE": 0.8,
}


def current_phase(es: EngineState, round_id: str, elapsed_frac: float) -> str:
    phase = "REQUIREMENTS"
    for p in PHASES:
        if elapsed_frac >= PHASE_SCHEDULE[p]:
            phase = p
    if phase != "REQUIREMENTS" and not es.intent_seen(round_id, "requirements_stated"):
        return "REQUIREMENTS"
    return phase


def component_coverage(reference: list[str], canvas_labels: list[str]) -> dict[str, Any]:
    """Deterministic diagram coverage: reference component present iff any
    canvas label fuzzily contains one of its keywords."""
    labels = " ".join(canvas_labels).lower()
    covered, missing = [], []
    for comp in reference:
        keys = [w for w in comp.lower().replace("/", " ").split() if len(w) > 2]
        (covered if any(k in labels for k in keys) else missing).append(comp)
    return {"covered": covered, "missing": missing,
            "coverage": round(len(covered) / len(reference), 2) if reference else 1.0}


def design_directive(es: EngineState, round_id: str, ctx: dict[str, Any]) -> str | None:
    q = ctx.get("design_question")
    if not q:
        return None
    elapsed_frac = float(ctx.get("elapsed_frac", 0.0))
    phase = current_phase(es, round_id, elapsed_frac)
    lines = [f"Design phase: {phase}."]

    if phase == "REQUIREMENTS":
        lines.append(
            "Requirements first. Answer scoping questions from this sheet: "
            + str(q.get("requirement_sheet"))
            + ' When they have stated functional + non-functional requirements, tag the '
            'turn intent "requirements_stated". If they start drawing boxes immediately, '
            'give exactly one nudge: "before we design — what are we actually building, '
            'and for how many users?"'
        )
    if phase == "ESTIMATION":
        blocks = q.get("estimation_blocks") or []
        if blocks:
            b = blocks[0]
            lines.append(
                f"Back-of-envelope block {b['id']}: reference {b['correct_value']} "
                f"(±{b.get('tolerance_pct', 5)}%). The engine adjudicates the number; "
                "confirm or correct only their final figure."
            )
    coverage = ctx.get("component_coverage") or {}
    if phase in ("HIGH_LEVEL_DESIGN", "DEEP_DIVE"):
        if coverage.get("missing"):
            lines.append(
                "Reference components not yet on the whiteboard: "
                + ", ".join(coverage["missing"][:4])
                + ". Do not name them — steer with questions."
            )
        if phase == "DEEP_DIVE" and coverage.get("coverage", 0) >= 0.6:
            dive = (q.get("dive_areas") or ["a core component"])[0]
            lines.append(f"Coverage is sufficient — drive the deep dive into: {dive}.")
    if phase == "SCALE_AND_FAILURE":
        if not es.intent_seen(round_id, "scale_question"):
            lines.append(
                'Ask the scale question ("what breaks first at 100x?"), tagged intent '
                '"scale_question".'
            )
        if not es.intent_seen(round_id, "failure_question"):
            lines.append(
                'Ask the failure question ("this component just died — what happens?"), '
                'tagged intent "failure_question".'
            )
    return "\n".join(lines)


register(
    RoundTypeDef(
        type="system_design",
        prompt_file="design_v1",
        tools=("canvas", "scratchpad"),
        completion_intents=("requirements_stated", "scale_question", "failure_question"),
        transition_hint=(
            "Introduce the design problem and make clear the whiteboard is theirs; "
            "you can see everything they draw."
        ),
        silence_maxhold_s=15,
        directive_extra=design_directive,
    )
)
