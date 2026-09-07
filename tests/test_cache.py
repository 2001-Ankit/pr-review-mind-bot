from conftest import StubLLM
from reviewmindbot.cache import (
    NullCache,
    ResponseCache,
    default_cache_path,
    diff_fingerprint,
    make_key,
)
from reviewmindbot.core.chunking import Chunk
from reviewmindbot.engine.reviewer import Reviewer


def cache_at(tmp_path, **kwargs):
    return ResponseCache(tmp_path / "cache.db", **kwargs)


class TestKeys:
    def test_same_inputs_produce_the_same_key(self):
        assert make_key("gemini", "m", "sys", "user") == make_key(
            "gemini", "m", "sys", "user"
        )

    def test_key_covers_provider_model_and_both_prompts(self):
        base = make_key("gemini", "m", "sys", "user")

        assert make_key("openai", "m", "sys", "user") != base
        assert make_key("gemini", "other", "sys", "user") != base
        assert make_key("gemini", "m", "changed", "user") != base
        assert make_key("gemini", "m", "sys", "changed") != base

    def test_schema_version_invalidates_old_entries(self):
        """A prompt or parser change must not serve stale cached findings."""
        import reviewmindbot.cache as cache_module

        before = make_key("gemini", "m", "sys", "user")
        original = cache_module.CACHE_SCHEMA_VERSION
        try:
            cache_module.CACHE_SCHEMA_VERSION = original + 1
            assert make_key("gemini", "m", "sys", "user") != before
        finally:
            cache_module.CACHE_SCHEMA_VERSION = original

    def test_diff_fingerprint_is_stable_and_short(self):
        assert diff_fingerprint("abc") == diff_fingerprint("abc")
        assert diff_fingerprint("abc") != diff_fingerprint("abd")
        assert len(diff_fingerprint("abc")) == 12


class TestStorage:
    def test_round_trip(self, tmp_path):
        with cache_at(tmp_path) as cache:
            cache.set("k", "value")

            assert cache.get("k") == "value"

    def test_missing_key_returns_none(self, tmp_path):
        with cache_at(tmp_path) as cache:
            assert cache.get("absent") is None

    def test_entries_expire(self, tmp_path):
        with cache_at(tmp_path, ttl_seconds=0) as cache:
            cache.set("k", "value")

            assert cache.get("k") is None

    def test_purge_removes_expired_rows(self, tmp_path):
        with cache_at(tmp_path, ttl_seconds=0) as cache:
            cache.set("k", "value")

            assert cache.purge_expired() == 1
            assert cache.stats()["entries"] == 0

    def test_clear_empties_the_cache(self, tmp_path):
        with cache_at(tmp_path) as cache:
            cache.set("a", "1")
            cache.set("b", "2")
            cache.clear()

            assert cache.stats()["entries"] == 0

    def test_survives_process_restart(self, tmp_path):
        with cache_at(tmp_path) as first:
            first.set("k", "persisted")

        with cache_at(tmp_path) as second:
            assert second.get("k") == "persisted"

    def test_unwritable_location_degrades_to_a_miss(self, tmp_path):
        """A broken cache must never fail a review."""
        blocker = tmp_path / "afile"
        blocker.write_text("not a directory", encoding="utf-8")

        cache = ResponseCache(blocker / "nested" / "cache.db")

        assert cache.enabled is False
        assert cache.get("k") is None
        cache.set("k", "v")  # must not raise

    def test_null_cache_never_stores(self):
        cache = NullCache()
        cache.set("k", "v")

        assert cache.get("k") is None
        assert cache.stats()["enabled"] is False

    def test_default_path_is_per_user_not_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        assert default_cache_path().parent != tmp_path
        assert default_cache_path().name == "cache.db"


class TestReviewerIntegration:
    def chunk(self):
        return Chunk(text="some diff", files=["a.py"])

    def test_second_review_of_the_same_chunk_costs_nothing(self, tmp_path):
        llm = StubLLM('[{"severity": "low", "category": "bug", "message": "x"}]')
        with cache_at(tmp_path) as cache:
            reviewer = Reviewer(llm, cache=cache)

            first = reviewer.review(self.chunk())
            second = reviewer.review(self.chunk())

        assert len(llm.calls) == 1
        assert [f.message for f in first] == [f.message for f in second]
        assert llm.usage.cached_requests == 1

    def test_a_different_chunk_is_not_served_from_cache(self, tmp_path):
        llm = StubLLM('[{"severity": "low", "category": "bug", "message": "x"}]')
        with cache_at(tmp_path) as cache:
            reviewer = Reviewer(llm, cache=cache)
            reviewer.review(Chunk(text="one", files=["a.py"]))
            reviewer.review(Chunk(text="two", files=["a.py"]))

        assert len(llm.calls) == 2

    def test_changing_the_model_bypasses_the_cache(self, tmp_path):
        with cache_at(tmp_path) as cache:
            first = StubLLM("[]")
            Reviewer(first, cache=cache).review(self.chunk())

            second = StubLLM("[]")
            second.model = "a-different-model"
            Reviewer(second, cache=cache).review(self.chunk())

            assert len(second.calls) == 1

    def test_no_cache_always_calls_the_model(self):
        llm = StubLLM("[]")
        reviewer = Reviewer(llm, cache=NullCache())

        reviewer.review(self.chunk())
        reviewer.review(self.chunk())

        assert len(llm.calls) == 2
