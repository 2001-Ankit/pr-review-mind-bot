import pytest

from reviewmindbot.config import Config
from reviewmindbot.errors import ConfigError, ProviderError
from reviewmindbot.llm.base import Completion, LLMProvider, _is_retryable
from reviewmindbot.llm.factory import available_providers, create_provider


class FlakyProvider(LLMProvider):
    name = "flaky"

    def __init__(self, *errors, final="ok", **kwargs):
        super().__init__(model="m", **kwargs)
        self.errors = list(errors)
        self.final = final
        self.attempts = 0

    def _complete(self, system_prompt, user_prompt):
        self.attempts += 1
        if self.errors:
            raise self.errors.pop(0)
        return Completion(text=self.final, input_tokens=10, output_tokens=5)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("reviewmindbot.llm.base.time.sleep", lambda _: None)


def test_transient_failure_is_retried():
    provider = FlakyProvider(RuntimeError("503 Service Unavailable"), max_retries=3)

    assert provider.generate("sys", "user") == "ok"
    assert provider.attempts == 2


def test_permanent_failure_is_not_retried():
    """An invalid API key will never succeed; burning three calls on it is waste."""
    provider = FlakyProvider(
        *[RuntimeError("400 invalid api key")] * 3, max_retries=3
    )

    with pytest.raises(ProviderError, match="1 attempt"):
        provider.generate("sys", "user")

    assert provider.attempts == 1


def test_retries_are_bounded():
    provider = FlakyProvider(*[RuntimeError("429 rate limit")] * 5, max_retries=3)

    with pytest.raises(ProviderError, match="3 attempt"):
        provider.generate("sys", "user")

    assert provider.attempts == 3


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (RuntimeError("429 Too Many Requests"), True),
        (RuntimeError("503 overloaded"), True),
        (RuntimeError("connection reset"), True),
        (RuntimeError("request timed out"), True),
        (RuntimeError("401 unauthorized"), False),
        (RuntimeError("model not found"), False),
    ],
)
def test_retry_classification(error, expected):
    assert _is_retryable(error) is expected


def test_status_code_attribute_wins_over_message():
    error = RuntimeError("something about a connection")
    error.status_code = 404

    assert _is_retryable(error) is False


def test_none_response_becomes_empty_string():
    assert FlakyProvider(final=None).generate("s", "u") == ""


class TestFactory:
    def test_registry_lists_all_providers(self):
        assert available_providers() == ["gemini", "groq", "openai"]

    def test_unknown_provider_is_rejected(self):
        with pytest.raises(ProviderError, match="Unknown provider"):
            create_provider("hal9000", Config())

    def test_missing_credential_is_reported_before_any_import(self):
        with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
            create_provider("openai", Config())
