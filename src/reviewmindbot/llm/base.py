"""Provider interface and shared retry behaviour."""

from __future__ import annotations

import abc
import logging
import random
import time
from dataclasses import dataclass

from ..errors import ProviderError
from ..usage import Usage, estimate_tokens

logger = logging.getLogger(__name__)


@dataclass
class Completion:
    """One model response plus whatever the provider reported about its cost.

    Token counts are taken from the provider when it reports them and estimated
    otherwise, so budgeting works uniformly across SDKs.
    """

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated: bool = False

    @classmethod
    def estimated_from(cls, text: str, prompt: str) -> Completion:
        return cls(
            text=text,
            input_tokens=estimate_tokens(prompt),
            output_tokens=estimate_tokens(text),
            estimated=True,
        )


class LLMProvider(abc.ABC):
    """A text-in / text-out model.

    Subclasses implement :meth:`_complete`; retries, usage accounting, logging
    and error wrapping are handled here so every provider behaves the same way.
    """

    name: str = "unknown"

    def __init__(self, model: str, *, timeout: int = 60, max_retries: int = 3) -> None:
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        #: Running totals for this provider instance.
        self.usage = Usage(model=model)

    @abc.abstractmethod
    def _complete(self, system_prompt: str, user_prompt: str) -> Completion:
        """Perform a single completion call. May raise anything."""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Complete a prompt, retrying transient failures with backoff."""
        last_error: Exception | None = None
        attempts = 0

        for attempt in range(1, self.max_retries + 1):
            attempts = attempt
            try:
                completion = self._complete(system_prompt, user_prompt)
            except Exception as exc:  # provider SDKs raise their own hierarchies
                last_error = exc
                if attempt == self.max_retries or not _is_retryable(exc):
                    break
                delay = min(2 ** (attempt - 1), 8) + random.uniform(0, 0.5)
                logger.warning(
                    "%s call failed (attempt %d/%d): %s - retrying in %.1fs",
                    self.name,
                    attempt,
                    self.max_retries,
                    exc,
                    delay,
                )
                time.sleep(delay)
                continue

            self.usage.record(
                self.model, completion.input_tokens, completion.output_tokens
            )
            return completion.text or ""

        raise ProviderError(
            f"{self.name} request failed after {attempts} attempt(s): {last_error}"
        ) from last_error


_RETRYABLE_MARKERS = (
    "429",
    "500",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "temporarily unavailable",
    "rate limit",
    "overloaded",
    "connection",
)


def _is_retryable(exc: Exception) -> bool:
    """Best-effort classification of transient provider failures.

    Each SDK has its own exception tree; matching on the rendered message keeps
    this provider-agnostic without importing all three SDKs eagerly.
    """
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if isinstance(status, int):
        return status == 429 or 500 <= status < 600

    text = str(exc).lower()
    return any(marker in text for marker in _RETRYABLE_MARKERS)
