import pytest

from reviewmindbot.config import Config
from reviewmindbot.llm.base import Completion, LLMProvider


class StubLLM(LLMProvider):
    """Returns canned responses and records the prompts it received."""

    name = "stub"

    def __init__(self, *responses: str, fail_with: Exception | None = None):
        super().__init__(model="stub-model", max_retries=1)
        self._responses = list(responses) or ["[]"]
        self._fail_with = fail_with
        self.calls: list[tuple[str, str]] = []

    def _complete(self, system_prompt: str, user_prompt: str) -> Completion:
        self.calls.append((system_prompt, user_prompt))
        if self._fail_with is not None:
            raise self._fail_with
        index = min(len(self.calls) - 1, len(self._responses) - 1)
        return Completion(
            text=self._responses[index], input_tokens=100, output_tokens=50
        )


@pytest.fixture
def stub_llm():
    return StubLLM


@pytest.fixture
def config():
    return Config(max_chunk_size=4000, chunk_overlap=0, max_concurrency=1)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """Keep the developer's real keys, cache and settings out of the tests."""
    for name in (
        "LLM_PROVIDER",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
        "GITHUB_TOKEN",
        "LOG_LEVEL",
        "LOG_FILE",
        "MAX_CHUNK_SIZE",
        "CHUNK_OVERLAP",
        "MAX_CONCURRENCY",
        "REVIEWMINDBOT_MODEL",
        "BUDGET_USD",
        "CACHE_TTL_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    # Redirect the per-user cache and state directories into the test's own
    # tmp_path: a test run must never read or write the developer's real cache.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    # Caching off by default so each test sees the stub response it set up.
    # The cache has its own dedicated tests that switch it back on.
    monkeypatch.setenv("CACHE_ENABLED", "0")


SAMPLE_DIFF = """diff --git a/example.py b/example.py
index 1111111..2222222 100644
--- a/example.py
+++ b/example.py
@@ -1,2 +1,3 @@
 line1
-old_value = 1
+new_value = 2
+print(new_value)
"""
