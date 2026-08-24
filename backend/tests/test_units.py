"""Unit tests that run without infrastructure."""

import pytest
from pydantic import ValidationError

from app.schemas import EventIn
from providers.base import ContextBlock, LLMRequest
from providers.pricing import estimate_cost_usd


def test_event_type_vocabulary_is_closed() -> None:
    EventIn(seq=0, type="stt_final", payload={})
    with pytest.raises(ValidationError):
        EventIn(seq=0, type="made_up_type", payload={})


def test_cost_estimate_haiku() -> None:
    # 1M input + 1M output on claude-haiku-4-5 = $1 + $5
    cost = estimate_cost_usd("claude-haiku-4-5", 1_000_000, 1_000_000)
    assert cost == pytest.approx(6.00)


def test_cost_estimate_cache_discount() -> None:
    # cache reads bill at 0.1x input rate
    cost = estimate_cost_usd("claude-opus-5", 0, 0, cache_read_tokens=1_000_000)
    assert cost == pytest.approx(0.50)


def test_cost_estimate_unknown_model_returns_none() -> None:
    assert estimate_cost_usd("some-future-model", 100, 100) is None


def test_openrouter_message_translation() -> None:
    from providers.openrouter_provider import build_openrouter_messages

    req = LLMRequest(
        model="anthropic/claude-haiku-4.5",
        system_blocks=[ContextBlock("stable prompt", cached=True), ContextBlock("fresh tail")],
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": [{"type": "text", "text": "hello"}]},
        ],
    )
    msgs = build_openrouter_messages(req)
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in msgs[0]["content"][1]
    assert msgs[1] == {"role": "user", "content": "hi"}
    assert msgs[2]["content"] == [{"type": "text", "text": "hello"}]


def test_llm_request_carries_cache_breakpoints() -> None:
    req = LLMRequest(
        model="claude-haiku-4-5",
        system_blocks=[ContextBlock("stable prompt", cached=True), ContextBlock("fresh tail")],
        messages=[{"role": "user", "content": "hi"}],
    )
    assert req.system_blocks[0].cached and not req.system_blocks[1].cached
