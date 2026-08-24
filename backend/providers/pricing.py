"""Cost estimation for llm_calls rows.

USD per 1M tokens, verified against Anthropic pricing 2026-08-23.
Cache reads bill at 0.1x input rate; cache writes at 1.25x.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    input_per_m: float
    output_per_m: float


PRICING: dict[str, ModelPricing] = {
    "claude-haiku-4-5": ModelPricing(input_per_m=1.00, output_per_m=5.00),
    "claude-opus-5": ModelPricing(input_per_m=5.00, output_per_m=25.00),
    "claude-sonnet-5": ModelPricing(input_per_m=3.00, output_per_m=15.00),
}

CACHE_READ_MULTIPLIER = 0.1
CACHE_WRITE_MULTIPLIER = 1.25


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float | None:
    pricing = PRICING.get(model)
    if pricing is None:
        return None
    per_input = pricing.input_per_m / 1_000_000
    per_output = pricing.output_per_m / 1_000_000
    return (
        input_tokens * per_input
        + cache_read_tokens * per_input * CACHE_READ_MULTIPLIER
        + cache_creation_tokens * per_input * CACHE_WRITE_MULTIPLIER
        + output_tokens * per_output
    )
