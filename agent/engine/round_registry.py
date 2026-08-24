"""T19 — round-type registry: a round type is data + plugin hooks, not a fork.

Invariant #15: nothing in the engine package (including registered round
types) may import from the voice path — enforced by tests/test_boundaries.py.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RoundTypeDef:
    type: str
    prompt_file: str                       # /prompts/conduct/<file>.txt
    tools: tuple[str, ...] = ()            # editor|scratchpad|canvas|exhibits
    is_code_round: bool = False            # code observation + hint/twist mechanics
    # intents that must appear (from @meta) before the round can wrap cleanly;
    # the engine steers toward missing ones in the last 30% of the budget
    completion_intents: tuple[str, ...] = ()
    transition_hint: str = ""
    silence_maxhold_s: float = 12.0
    # optional plugin hooks (pure functions):
    #   directive_extra(es, round_id, ctx: dict) -> str | None
    directive_extra: Callable[..., str | None] | None = field(default=None, compare=False)
    #   observation_builder(ctx: dict) -> str | None   (BLOCK D content)
    observation_builder: Callable[..., str | None] | None = field(default=None, compare=False)


_REGISTRY: dict[str, RoundTypeDef] = {}


def register(defn: RoundTypeDef) -> RoundTypeDef:
    _REGISTRY[defn.type] = defn
    return defn


def get_round_type(type_: str) -> RoundTypeDef:
    return _REGISTRY.get(type_) or RoundTypeDef(type=type_, prompt_file="warmup_v1")


def registered_types() -> list[str]:
    return sorted(_REGISTRY)


def tools_for(type_: str) -> tuple[str, ...]:
    return get_round_type(type_).tools


def completion_intents_for(type_: str) -> tuple[str, ...]:
    return get_round_type(type_).completion_intents


def round_context(**kwargs: Any) -> dict[str, Any]:
    """Loose context bag passed to plugin hooks (engine state, pack data,
    live signals) — keeps hook signatures stable as plugins grow."""
    return kwargs
