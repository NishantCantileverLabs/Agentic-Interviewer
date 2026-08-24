import time
from collections.abc import AsyncIterator
from typing import Any

from anthropic import AsyncAnthropic

from app.config import get_settings
from providers.base import LLMProvider, LLMRequest, LLMResult, LLMStream


def _build_system(request: LLMRequest) -> list[dict[str, Any]]:
    """Render ContextBlocks to Messages-API system blocks with cache breakpoints.

    Anthropic prompt caching is a prefix match; the caller guarantees block
    order stability (engine layout §6.3). Max 4 breakpoints per request.
    """
    cache_enabled = get_settings().prompt_cache_enabled
    blocks: list[dict[str, Any]] = []
    for cb in request.system_blocks:
        block: dict[str, Any] = {"type": "text", "text": cb.text}
        if cb.cached and cache_enabled:
            block["cache_control"] = {"type": "ephemeral"}
        blocks.append(block)
    return blocks


def _result_from_message(message: Any, ttft_ms: int | None, total_ms: int) -> LLMResult:
    text = "".join(b.text for b in message.content if b.type == "text")
    usage = message.usage
    return LLMResult(
        text=text,
        model=message.model,
        stop_reason=message.stop_reason,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        ttft_ms=ttft_ms,
        total_ms=total_ms,
    )


class _AnthropicStream(LLMStream):
    def __init__(self, client: AsyncAnthropic, kwargs: dict[str, Any]) -> None:
        self._client = client
        self._kwargs = kwargs
        self._result: LLMResult | None = None

    def __aiter__(self) -> AsyncIterator[str]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[str]:
        start = time.monotonic()
        ttft_ms: int | None = None
        async with self._client.messages.stream(**self._kwargs) as stream:
            async for text in stream.text_stream:
                if ttft_ms is None:
                    ttft_ms = int((time.monotonic() - start) * 1000)
                yield text
            message = await stream.get_final_message()
        total_ms = int((time.monotonic() - start) * 1000)
        self._result = _result_from_message(message, ttft_ms, total_ms)

    def result(self) -> LLMResult:
        if self._result is None:
            raise RuntimeError("stream not yet exhausted")
        return self._result


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or get_settings().anthropic_api_key or None
        self._client = AsyncAnthropic(api_key=key) if key else AsyncAnthropic()

    def _kwargs(self, request: LLMRequest) -> dict[str, Any]:
        return {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "system": _build_system(request),
            "messages": request.messages,
            **request.extra,
        }

    async def complete(self, request: LLMRequest) -> LLMResult:
        start = time.monotonic()
        message = await self._client.messages.create(**self._kwargs(request))
        total_ms = int((time.monotonic() - start) * 1000)
        return _result_from_message(message, None, total_ms)

    async def stream(self, request: LLMRequest) -> LLMStream:
        return _AnthropicStream(self._client, self._kwargs(request))
