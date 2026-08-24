"""Backend mirror of the agent's round-type registry — drives candidate tool
panels and plan validation only (behaviors live agent-side in engine/rounds)."""

ROUND_TOOLS: dict[str, tuple[str, ...]] = {
    "intro": (),
    "warmup": (),
    "discussion": (),
    "coding": ("editor",),
    "sql": ("editor",),
    "case": ("scratchpad", "exhibits"),
    "system_design": ("canvas", "scratchpad"),
    "behavioral": (),
    "wrapup": (),
    "echo": (),
}

CONTENT_KEYS = ("question", "case_pack", "design_question", "sql_dataset")

ROUND_TYPES = tuple(ROUND_TOOLS)


def tools_for(round_type: str) -> tuple[str, ...]:
    return ROUND_TOOLS.get(round_type, ())
