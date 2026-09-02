"""Conversation-only round types."""

from engine.round_registry import RoundTypeDef, register

register(RoundTypeDef(type="intro", prompt_file="intro_v1", silence_maxhold_s=4))
register(
    RoundTypeDef(
        type="warmup",
        prompt_file="warmup_v1",
        silence_maxhold_s=4,
        transition_hint="Ask what they have been building recently.",
    )
)
register(
    RoundTypeDef(
        type="discussion",
        prompt_file="technical_deepdive_v1",
        silence_maxhold_s=8,
        transition_hint="Shift into deeper technical territory on their strongest thread.",
    )
)
register(
    RoundTypeDef(
        type="wrapup",
        prompt_file="wrapup_v1",
        silence_maxhold_s=4,
        transition_hint="Wind down: thank them for the rounds and invite their questions.",
    )
)
# Dummy type used by the T19 acceptance test: registers end-to-end without
# touching any core file.
register(RoundTypeDef(type="echo", prompt_file="warmup_v1", transition_hint="Echo round."))
