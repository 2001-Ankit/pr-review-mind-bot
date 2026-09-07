import pytest

from reviewmindbot.usage import (
    Budget,
    BudgetExceeded,
    Usage,
    cost_of,
    estimate_tokens,
    format_usage,
    price_for,
)


class TestEstimation:
    def test_token_estimate_scales_with_length(self):
        assert estimate_tokens("x" * 350) == pytest.approx(100, rel=0.1)

    def test_empty_text_still_costs_a_token(self):
        assert estimate_tokens("") == 1

    def test_known_model_is_priced(self):
        assert price_for("gpt-4o-mini") == (0.15, 0.60)

    def test_dated_and_prefixed_model_ids_resolve(self):
        """Providers append dates and prefixes; budgeting must still work."""
        assert price_for("gpt-4o-mini-2024-07-18") == price_for("gpt-4o-mini")
        assert price_for("openai/gpt-oss-20b") is not None

    def test_unknown_model_has_no_price(self):
        assert price_for("some-local-llama") is None

    def test_unknown_model_costs_zero_rather_than_guessing(self):
        assert cost_of("some-local-llama", 1_000_000, 1_000_000) == 0.0

    def test_cost_uses_separate_input_and_output_rates(self):
        # gpt-4o-mini: $0.15 in, $0.60 out per 1M tokens.
        assert cost_of("gpt-4o-mini", 1_000_000, 0) == pytest.approx(0.15)
        assert cost_of("gpt-4o-mini", 0, 1_000_000) == pytest.approx(0.60)


class TestUsage:
    def test_accumulates_across_requests(self):
        usage = Usage()
        usage.record("gpt-4o-mini", 1000, 500)
        usage.record("gpt-4o-mini", 1000, 500)

        assert usage.requests == 2
        assert usage.total_tokens == 3000
        assert usage.cost_usd == pytest.approx(cost_of("gpt-4o-mini", 2000, 1000))

    def test_cache_hits_are_counted_separately_and_cost_nothing(self):
        usage = Usage(model="gpt-4o-mini")
        usage.record_cache_hit()
        usage.record_cache_hit()

        assert usage.cached_requests == 2
        assert usage.requests == 0
        assert usage.cost_usd == 0.0

    def test_unpriced_model_reports_null_cost(self):
        usage = Usage()
        usage.record("mystery-model", 100, 100)

        assert usage.priced is False
        assert usage.to_dict()["cost_usd"] is None

    def test_concurrent_records_are_not_lost(self):
        """Chunks are reviewed in parallel, so accounting must be thread-safe."""
        from concurrent.futures import ThreadPoolExecutor

        usage = Usage()
        with ThreadPoolExecutor(max_workers=8) as pool:
            for _ in range(200):
                pool.submit(usage.record, "gpt-4o-mini", 10, 10)

        assert usage.requests == 200
        assert usage.total_tokens == 4000


class TestBudget:
    def test_allows_requests_under_the_limit(self):
        budget = Budget(1.00, "gpt-4o-mini")
        usage = Usage(model="gpt-4o-mini")

        budget.check(usage, "a short prompt")

    def test_blocks_the_request_that_would_break_the_limit(self):
        """Checked before spending, so the limit is a limit."""
        budget = Budget(0.0001, "gpt-4o-mini")
        usage = Usage(model="gpt-4o-mini")
        usage.record("gpt-4o-mini", 500_000, 0)

        with pytest.raises(BudgetExceeded, match="Budget of"):
            budget.check(usage, "x" * 100_000)

    def test_no_limit_means_no_enforcement(self):
        budget = Budget(None, "gpt-4o-mini")

        assert budget.enforceable is False
        budget.check(Usage(), "x" * 1_000_000)

    def test_unpriced_model_cannot_be_enforced(self):
        """Without a price there is no way to know when the limit is hit."""
        budget = Budget(0.01, "mystery-model")

        assert budget.enforceable is False
        budget.check(Usage(), "x" * 1_000_000)


class TestFormatting:
    def test_reports_requests_tokens_and_cost(self):
        usage = Usage()
        usage.record("gpt-4o-mini", 1000, 500)

        text = format_usage(usage)

        assert "1 request(s)" in text
        assert "1,500 tokens" in text
        assert "$" in text

    def test_mentions_cache_hits(self):
        usage = Usage(model="gpt-4o-mini")
        usage.record_cache_hit()

        assert "1 from cache" in format_usage(usage)

    def test_says_so_when_the_price_is_unknown(self):
        usage = Usage()
        usage.record("mystery-model", 10, 10)

        assert "cost unknown" in format_usage(usage)
