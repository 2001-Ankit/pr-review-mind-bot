"""Single place that maps a provider name to a live client.

Adding a provider used to mean editing the argparse choices, the config
key lookup, and an if/elif chain in ``main()``. Now it means adding one entry
to :data:`PROVIDERS` -- the CLI choices and config validation both derive from
the same table.
"""

from __future__ import annotations

from collections.abc import Callable

from ..config import Config
from ..errors import ProviderError
from .base import LLMProvider


def _gemini(api_key: str, model: str, **kwargs) -> LLMProvider:
    from .gemini import GeminiProvider

    return GeminiProvider(api_key, model, **kwargs)


def _openai(api_key: str, model: str, **kwargs) -> LLMProvider:
    from .openai import OpenAIProvider

    return OpenAIProvider(api_key, model, **kwargs)


def _groq(api_key: str, model: str, **kwargs) -> LLMProvider:
    from .openai import GroqProvider

    return GroqProvider(api_key, model, **kwargs)


PROVIDERS: dict[str, Callable[..., LLMProvider]] = {
    "gemini": _gemini,
    "openai": _openai,
    "groq": _groq,
}


def available_providers() -> list[str]:
    return sorted(PROVIDERS)


def create_provider(provider: str, config: Config) -> LLMProvider:
    """Build the configured provider, validating its credential first."""
    provider = provider.lower()
    factory = PROVIDERS.get(provider)
    if factory is None:
        raise ProviderError(
            f"Unknown provider: {provider}. "
            f"Available: {', '.join(available_providers())}"
        )

    api_key = config.api_key_for(provider)
    model = config.resolve_model(provider)

    try:
        return factory(
            api_key,
            model,
            timeout=config.request_timeout,
            max_retries=config.max_retries,
        )
    except ImportError as exc:
        raise ProviderError(
            f"The {provider} provider needs an extra dependency: {exc}. "
            f"Install it with: pip install 'reviewmindbot[{provider}]'"
        ) from exc
