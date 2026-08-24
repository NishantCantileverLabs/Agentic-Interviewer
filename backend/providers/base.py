"""LLM provider abstraction (PHASE1_ARCHITECTURE.md D2/D5/D7).

Callers build requests out of ContextBlocks so cache-boundary placement stays
under caller control (the engine's cache-stable A/B/C/D layout, §6.3) while
providers stay swappable. Every call site must persist the returned LLMResult
to `llm_calls` with a real prompt_version_id — that wiring lives with the
caller, not here.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextBlock:
    """One block of system context; `cached` marks a cache breakpoint after it."""

    text: str
    cached: bool = False


@dataclass
class LLMRequest:
    model: str
    system_blocks: list[ContextBlock]
    messages: list[dict[str, Any]]  # Messages-API shape, caller-controlled
    max_tokens: int = 1024
    extra: dict[str, Any] = field(default_factory=dict)  # provider-specific passthrough


@dataclass
class LLMResult:
    text: str
    model: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    ttft_ms: int | None
    total_ms: int
    # Provider-reported actual cost (OpenRouter returns this); when None the
    # caller estimates via providers/pricing.py.
    cost_usd: float | None = None


class LLMStream(ABC):
    """Async iterator of text deltas; `result()` is valid after exhaustion."""

    @abstractmethod
    def __aiter__(self) -> AsyncIterator[str]: ...

    @abstractmethod
    def result(self) -> LLMResult: ...


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResult:
        """Non-streaming call (eval worker, tests)."""

    @abstractmethod
    async def stream(self, request: LLMRequest) -> LLMStream:
        """Streaming call (voice path). Deltas must be yielded as they arrive —
        buffering the full response before returning violates latency discipline."""
