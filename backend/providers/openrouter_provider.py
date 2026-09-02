"""OpenRouter provider — OpenAI-compatible chat completions over httpx.

Lets an OpenRouter API key be plugged in as an alternative to first-party
Anthropic access. Model names use OpenRouter slugs (e.g.
"anthropic/claude-haiku-4.5"). `cache_control` breakpoints are passed through
on system content parts — OpenRouter forwards them to Anthropic-family models,
other models ignore them.
"""

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import get_settings
from providers.base import LLMProvider, LLMRequest, LLMResult, LLMStream

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def build_openrouter_messages(request: LLMRequest) -> list[dict[str, Any]]:
    """Translate LLMRequest (Anthropic-shaped) to OpenAI-style messages."""
    cache_enabled = get_settings().prompt_cache_enabled
    system_parts: list[dict[str, Any]] = []
    for cb in request.system_blocks:
        part: dict[str, Any] = {"type": "text", "text": cb.text}
        if cb.cached and cache_enabled:
            part["cache_control"] = {"type": "ephemeral"}
        system_parts.append(part)

    messages: list[dict[str, Any]] = []
    if system_parts:
        messages.append({"role": "system", "content": system_parts})

    for m in request.messages:
        content = m["content"]
        if isinstance(content, list):
            content = [
                {"type": "text", "text": b["text"]} for b in content if b.get("type") == "text"
            ]
        messages.append({"role": m["role"], "content": content})
    return messages


def _usage_fields(usage: dict[str, Any]) -> tuple[int, int, int, float | None]:
    prompt = int(usage.get("prompt_tokens", 0))
    completion = int(usage.get("completion_tokens", 0))
    details = usage.get("prompt_tokens_details") or {}
    cached = int(details.get("cached_tokens", 0))
    cost = usage.get("cost")
    return prompt, completion, cached, float(cost) if cost is not None else None


class _OpenRouterStream(LLMStream):
    def __init__(self, client: httpx.AsyncClient, body: dict[str, Any], model: str) -> None:
        self._client = client
        self._body = body
        self._model = model
        self._result: LLMResult | None = None

    def __aiter__(self) -> AsyncIterator[str]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[str]:
        start = time.monotonic()
        ttft_ms: int | None = None
        text_parts: list[str] = []
        usage: dict[str, Any] = {}
        stop_reason: str | None = None

        async with self._client.stream("POST", "/chat/completions", json=self._body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[len("data: ") :]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if chunk.get("usage"):
                    usage = chunk["usage"]
                for choice in chunk.get("choices", []):
                    if choice.get("finish_reason"):
                        stop_reason = choice["finish_reason"]
                    delta = (choice.get("delta") or {}).get("content")
                    if delta:
                        if ttft_ms is None:
                            ttft_ms = int((time.monotonic() - start) * 1000)
                        text_parts.append(delta)
                        yield delta

        total_ms = int((time.monotonic() - start) * 1000)
        prompt, completion, cached, cost = _usage_fields(usage)
        self._result = LLMResult(
            text="".join(text_parts),
            model=self._model,
            stop_reason=stop_reason,
            input_tokens=prompt,
            output_tokens=completion,
            cache_read_tokens=cached,
            cache_creation_tokens=0,
            ttft_ms=ttft_ms,
            total_ms=total_ms,
            cost_usd=cost,
        )

    def result(self) -> LLMResult:
        if self._result is None:
            raise RuntimeError("stream not yet exhausted")
        return self._result


class OpenRouterProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        settings = get_settings()
        key = api_key or settings.openrouter_api_key
        if not key:
            raise ValueError("OPENROUTER_API_KEY is not set")
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.openrouter_base_url or DEFAULT_BASE_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "X-Title": "AI Interview Platform",
            },
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

    def _body(self, request: LLMRequest, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "messages": build_openrouter_messages(request),
            "usage": {"include": True},
            **request.extra,
        }
        if stream:
            body["stream"] = True
        return body

    async def complete(self, request: LLMRequest) -> LLMResult:
        start = time.monotonic()
        resp = await self._client.post("/chat/completions", json=self._body(request, stream=False))
        resp.raise_for_status()
        data = resp.json()
        total_ms = int((time.monotonic() - start) * 1000)
        choice = data["choices"][0]
        prompt, completion, cached, cost = _usage_fields(data.get("usage") or {})
        return LLMResult(
            text=choice["message"]["content"] or "",
            model=data.get("model", request.model),
            stop_reason=choice.get("finish_reason"),
            input_tokens=prompt,
            output_tokens=completion,
            cache_read_tokens=cached,
            cache_creation_tokens=0,
            ttft_ms=None,
            total_ms=total_ms,
            cost_usd=cost,
        )

    async def stream(self, request: LLMRequest) -> LLMStream:
        return _OpenRouterStream(self._client, self._body(request, stream=True), request.model)
