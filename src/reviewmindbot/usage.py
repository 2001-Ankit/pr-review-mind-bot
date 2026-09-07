"""Token accounting, pricing and budget enforcement.

An LLM tool that runs on every pull request has unbounded spend by default: a
1000-file PR is a 1000-file bill. Every run therefore carries a budget, and the
orchestrator stops dispatching work once the estimate would exceed it.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from .errors import ReviewMindBotError

#: USD per 1M tokens, as (input, output). Approximate and provider-published;
#: used for budgeting, not billing. Unknown models price at 0 and are reported
#: as "unpriced" rather than silently treated as free.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # Google
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),
    # OpenAI
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    # Anthropic
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    # Groq
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
    "openai/gpt-oss-20b": (0.10, 0.50),
}

#: Characters per token. A deliberately conservative approximation -- real
#: tokenizers differ per model and pulling one in per provider is not worth a
#: dependency for a pre-flight estimate.
CHARS_PER_TOKEN = 3.5


class BudgetExceeded(ReviewMindBotError):
    """Raised when a run would cost more than the configured budget."""


def estimate_tokens(text: str) -> int:
    """Rough token count for budgeting before a request is made."""
    return max(1, int(len(text) / CHARS_PER_TOKEN))


def price_for(model: str) -> tuple[float, float] | None:
    """Return ``(input, output)`` USD per 1M tokens, or None if unknown."""
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    # Providers prefix or date-suffix model ids ("openai/gpt-oss-20b",
    # "gpt-4o-mini-2024-07-18"); match the longest known id that fits.
    candidates = [key for key in MODEL_PRICING if key in model or model in key]
    if not candidates:
        return None
    return MODEL_PRICING[max(candidates, key=len)]


def cost_of(model: str, input_tokens: int, output_tokens: int) -> float:
    """USD cost of a call, or 0.0 when the model is not in the price table."""
    price = price_for(model)
    if price is None:
        return 0.0
    input_price, output_price = price
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


@dataclass
class Usage:
    """Accumulated token and cost totals for a run. Thread-safe."""

    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0
    cached_requests: int = 0
    cost_usd: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def priced(self) -> bool:
        """False when the model is absent from the price table."""
        return price_for(self.model) is not None

    def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        with self._lock:
            self.model = model or self.model
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
            self.requests += 1
            self.cost_usd += cost_of(model, input_tokens, output_tokens)

    def record_cache_hit(self) -> None:
        with self._lock:
            self.cached_requests += 1

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "requests": self.requests,
            "cached_requests": self.cached_requests,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6) if self.priced else None,
        }


class Budget:
    """A spend ceiling for one run.

    Checked before each request rather than after, so the limit is a limit and
    not a post-mortem.
    """

    def __init__(self, limit_usd: float | None, model: str) -> None:
        self.limit_usd = limit_usd
        self.model = model
        self._price = price_for(model)

    @property
    def enforceable(self) -> bool:
        """A budget on an unpriced model cannot be enforced, only reported."""
        return self.limit_usd is not None and self._price is not None

    def estimate_cost(self, prompt: str, expected_output_tokens: int = 800) -> float:
        return cost_of(self.model, estimate_tokens(prompt), expected_output_tokens)

    def check(self, usage: Usage, next_prompt: str) -> None:
        """Raise :class:`BudgetExceeded` if this request would break the limit."""
        if not self.enforceable:
            return

        projected = usage.cost_usd + self.estimate_cost(next_prompt)
        if projected > self.limit_usd:
            raise BudgetExceeded(
                f"Budget of ${self.limit_usd:.2f} reached "
                f"(spent ${usage.cost_usd:.4f}, next request ~"
                f"${self.estimate_cost(next_prompt):.4f}). "
                "Raise --budget-usd or narrow the diff."
            )


def format_usage(usage: Usage) -> str:
    """One-line human summary of what a run cost."""
    parts = [
        f"{usage.requests} request(s)",
        f"{usage.total_tokens:,} tokens",
    ]
    if usage.cached_requests:
        parts.append(f"{usage.cached_requests} from cache")
    if usage.priced:
        parts.append(f"~${usage.cost_usd:.4f}")
    else:
        parts.append(f"cost unknown (no price for {usage.model})")
    return ", ".join(parts)
