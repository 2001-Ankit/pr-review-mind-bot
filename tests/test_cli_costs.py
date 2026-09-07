"""CLI behaviour for cost control and PR publishing."""

import json
from unittest.mock import Mock

import pytest

from conftest import SAMPLE_DIFF, StubLLM
from reviewmindbot import cli
from reviewmindbot.usage import BudgetExceeded


@pytest.fixture
def diff_file(tmp_path):
    path = tmp_path / "changes.diff"
    path.write_text(SAMPLE_DIFF, encoding="utf-8")
    return str(path)


@pytest.fixture
def stub_provider(monkeypatch):
    def install(response="[]", llm=None):
        llm = llm or StubLLM(response)
        monkeypatch.setattr(cli, "create_provider", lambda provider, config: llm)
        monkeypatch.setattr("reviewmindbot.api.create_provider", lambda *a, **k: llm)
        return llm

    return install


class TestEstimate:
    def test_reports_projected_cost_without_calling_the_model(
        self, diff_file, stub_provider, capsys
    ):
        llm = stub_provider("[]")

        assert cli.main([diff_file, "--estimate"]) == cli.EXIT_OK

        out = capsys.readouterr().out
        assert "Requests:" in out
        assert "Estimated cost:" in out
        assert llm.calls == [], "--estimate must not spend anything"

    def test_says_so_when_the_model_has_no_published_price(
        self, diff_file, stub_provider, capsys
    ):
        stub_provider("[]")

        cli.main([diff_file, "--estimate", "--model", "some-local-llama"])

        assert "unknown" in capsys.readouterr().out


class TestBudget:
    def test_budget_stops_the_run_and_still_reports(self, diff_file, monkeypatch, capsys):
        """A spend ceiling must degrade to a partial review, not an error."""

        def refuse(self, usage, prompt):
            raise BudgetExceeded("Budget of $0.01 reached")

        monkeypatch.setattr("reviewmindbot.usage.Budget.check", refuse)
        llm = StubLLM("[]")
        monkeypatch.setattr(cli, "create_provider", lambda provider, config: llm)
        monkeypatch.setattr("reviewmindbot.api.create_provider", lambda *a, **k: llm)

        code = cli.main([diff_file, "--budget-usd", "0.01", "--output", "json"])

        assert code == cli.EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        assert payload["summary"]["budget_exhausted"] is True
        assert payload["summary"]["complete"] is False
        assert llm.calls == []

    def test_usage_is_reported_in_json(self, diff_file, stub_provider, capsys):
        stub_provider("[]")

        cli.main([diff_file, "--output", "json"])

        payload = json.loads(capsys.readouterr().out)
        assert payload["usage"]["requests"] == 1
        assert payload["usage"]["total_tokens"] == 150

    def test_cost_appears_in_text_output(self, diff_file, stub_provider, capsys):
        llm = StubLLM("[]")
        llm.model = "gpt-4o-mini"
        stub_provider(llm=llm)

        cli.main([diff_file])

        assert "Cost:" in capsys.readouterr().out


class TestCacheFlags:
    def test_clear_cache_exits_without_reviewing(self, capsys):
        assert cli.main(["--clear-cache"]) == cli.EXIT_OK
        assert "Cache cleared" in capsys.readouterr().out

    def test_no_cache_disables_the_cache(self, diff_file, stub_provider, monkeypatch):
        built = {}

        def spy(config):
            built["enabled"] = config.cache_enabled
            from reviewmindbot.cache import NullCache

            return NullCache()

        monkeypatch.setattr(cli.api, "build_cache", spy)
        stub_provider("[]")

        cli.main([diff_file, "--no-cache"])

        assert built["enabled"] is False


class TestComment:
    def test_comment_requires_a_pr(self, diff_file, stub_provider, capsys):
        stub_provider("[]")

        assert cli.main([diff_file, "--comment"]) == cli.EXIT_ERROR
        assert "--pr" in capsys.readouterr().err

    def test_comment_requires_a_github_token(self, stub_provider, monkeypatch, capsys):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        stub_provider("[]")

        code = cli.main(["--pr", "https://github.com/o/r/pull/1", "--comment"])

        assert code == cli.EXIT_ERROR
        assert "GITHUB_TOKEN" in capsys.readouterr().err

    def test_findings_are_published_to_the_pr(self, monkeypatch, stub_provider, capsys):
        monkeypatch.setenv("GITHUB_TOKEN", "t")
        stub_provider('[{"severity": "high", "category": "bug", "message": "Boom"}]')
        monkeypatch.setattr(cli.api, "load_diff", lambda **kwargs: SAMPLE_DIFF)

        published = Mock()
        published.describe.return_value = "summary comment created"
        publish = Mock(return_value=published)
        monkeypatch.setattr(cli, "publish_review", publish)
        monkeypatch.setattr(cli, "GitHubClient", Mock())

        code = cli.main(["--pr", "https://github.com/o/r/pull/1", "--comment"])

        assert code == cli.EXIT_OK
        assert publish.call_count == 1
        assert publish.call_args[1]["inline"] is True

    def test_no_inline_is_passed_through(self, monkeypatch, stub_provider):
        monkeypatch.setenv("GITHUB_TOKEN", "t")
        stub_provider("[]")
        monkeypatch.setattr(cli.api, "load_diff", lambda **kwargs: SAMPLE_DIFF)

        publish = Mock()
        monkeypatch.setattr(cli, "publish_review", publish)
        monkeypatch.setattr(cli, "GitHubClient", Mock())

        cli.main(["--pr", "https://github.com/o/r/pull/1", "--comment", "--no-inline"])

        assert publish.call_args[1]["inline"] is False


class TestOutputEncoding:
    def test_markdown_with_emoji_survives_a_legacy_console(
        self, diff_file, stub_provider, monkeypatch, capsys
    ):
        """Windows consoles default to cp1252; emoji must not kill the run."""
        stub_provider('[{"severity": "high", "category": "bug", "message": "Boom"}]')

        recorded = {}

        class LegacyStdout:
            encoding = "cp1252"

            def reconfigure(self, **kwargs):
                recorded.update(kwargs)

            def write(self, text):
                text.encode(recorded.get("encoding", self.encoding))
                return len(text)

            def flush(self):
                pass

        monkeypatch.setattr("sys.stdout", LegacyStdout())

        assert cli.main([diff_file, "--output", "markdown"]) == cli.EXIT_OK
        assert recorded["encoding"] == "utf-8"

    def test_partial_review_markdown_contains_a_warning_glyph(self):
        from reviewmindbot.engine.models import ReviewResult
        from reviewmindbot.reporting.formatters import format_markdown

        body = format_markdown(ReviewResult(failed_chunks=1))

        assert "Partial review" in body
        body.encode("utf-8")
