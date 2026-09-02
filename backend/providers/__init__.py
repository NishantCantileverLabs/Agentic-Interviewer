from app.config import get_settings
from providers.anthropic_provider import AnthropicProvider
from providers.base import ContextBlock, LLMProvider, LLMRequest, LLMResult, LLMStream
from providers.openrouter_provider import OpenRouterProvider

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "anthropic": AnthropicProvider,
    "openrouter": OpenRouterProvider,
}


def get_provider(name: str | None = None) -> LLMProvider:
    """Resolve a provider by name, defaulting to the LLM_PROVIDER setting."""
    resolved = name or get_settings().llm_provider
    try:
        return _PROVIDERS[resolved]()
    except KeyError:
        known = sorted(_PROVIDERS)
        raise ValueError(f"unknown LLM provider {resolved!r}; known: {known}") from None


__all__ = [
    "ContextBlock",
    "LLMProvider",
    "LLMRequest",
    "LLMResult",
    "LLMStream",
    "get_provider",
]
