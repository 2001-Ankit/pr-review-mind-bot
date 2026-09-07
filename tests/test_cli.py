import json

import pytest

from conftest import SAMPLE_DIFF, StubLLM
from reviewmindbot import cli
from reviewmindbot.engine.models import Category, Finding, ReviewResult, Severity
from reviewmindbot.errors import ProviderError
from reviewmindbot.reporting.formatters import format_json, format_markdown, format_text


@pytest.fixture
def diff_file(tmp_path):
    path = tmp_path / "changes.diff"
    path.write_text(SAMPLE_DIFF, encoding="utf-8")
    return str(path)


@pytest.fixture
def stub_provider(monkeypatch):
    """Replace the real provider factory with a canned-response stub."""

    def install(response="[]"):
        llm = StubLLM(response)
        monkeypatch.setattr(cli, "create_provider", lambda provider, config: llm)
        monkeypatch.setattr("reviewmindbot.api.create_provider", lambda *a, **k: llm)
        return llm

    return install


class TestExitCodes:
    def test_clean_review_exits_zero(self, diff_file, stub_provider, capsys):
        stub_provider("[]")

        assert cli.main([diff_file]) == cli.EXIT_OK
        assert "No issues found" in capsys.readouterr().out

    def test_findings_alone_do_not_fail_the_build(self, diff_file, stub_provider):
        stub_provider('[{"severity": "high", "category": "bug", "message": "Boom"}]')

        assert cli.main([diff_file]) == cli.EXIT_OK

    def test_fail_on_high_gates_the_build(self, diff_file, stub_provider):
        """Without this the tool always exited 0 and was useless in CI."""
        stub_provider('[{"severity": "high", "category": "bug", "message": "Boom"}]')

        assert cli.main([diff_file, "--fail-on", "high"]) == cli.EXIT_FINDINGS

    def test_fail_on_high_ignores_lower_severities(self, diff_file, stub_provider):
        stub_provider('[{"severity": "low", "category": "style", "message": "Nit"}]')

        assert cli.main([diff_file, "--fail-on", "high"]) == cli.EXIT_OK

    def test_fail_on_low_catches_everything(self, diff_file, stub_provider):
        stub_provider('[{"severity": "low", "category": "style", "message": "Nit"}]')

        assert cli.main([diff_file, "--fail-on", "low"]) == cli.EXIT_FINDINGS

    def test_missing_file_reports_cleanly(self, stub_provider, capsys):
        stub_provider()

        assert cli.main(["does-not-exist.diff"]) == cli.EXIT_ERROR
        assert "not found" in capsys.readouterr().err.lower()

    def test_provider_failure_reports_cleanly(self, diff_file, monkeypatch, capsys):
        def boom(provider, config):
            raise ProviderError("no API key")

        monkeypatch.setattr(cli, "create_provider", boom)

        assert cli.main([diff_file]) == cli.EXIT_ERROR
        assert "no API key" in capsys.readouterr().err


class TestArguments:
    def test_no_arguments_prints_help(self, capsys):
        assert cli.main([]) == cli.EXIT_OK
        assert "usage:" in capsys.readouterr().out

    def test_file_and_pr_together_are_rejected(self, diff_file):
        with pytest.raises(SystemExit):
            cli.main([diff_file, "--pr", "https://github.com/o/r/pull/1"])

    def test_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            cli.main(["--version"])

        assert exc.value.code == 0
        assert "reviewmindbot" in capsys.readouterr().out

    def test_stdin_is_accepted(self, stub_provider, monkeypatch, capsys):
        stub_provider("[]")
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(SAMPLE_DIFF))

        assert cli.main(["-"]) == cli.EXIT_OK
        assert "REVIEW RESULTS" in capsys.readouterr().out

    def test_json_output_is_machine_readable(self, diff_file, stub_provider, capsys):
        stub_provider('[{"severity": "high", "category": "bug", "message": "Boom"}]')

        cli.main([diff_file, "--output", "json"])

        payload = json.loads(capsys.readouterr().out)
        assert payload["summary"]["total"] == 1
        assert payload["summary"]["high"] == 1
        assert payload["findings"][0]["file_name"] == "example.py"

    def test_empty_diff_file_is_not_an_error(self, tmp_path, stub_provider, capsys):
        stub_provider()
        empty = tmp_path / "empty.diff"
        empty.write_text("", encoding="utf-8")

        assert cli.main([str(empty)]) == cli.EXIT_OK


class TestFormatters:
    def result(self):
        return ReviewResult(
            findings=[
                Finding(Severity.HIGH, Category.BUG, "Boom", "a.py", 10, "Fix it"),
                Finding(Severity.LOW, Category.STYLE, "Nit", "b.py"),
            ],
            files_reviewed=2,
            chunks_reviewed=2,
        )

    def test_text_groups_by_severity(self):
        output = format_text(self.result())

        assert "HIGH SEVERITY (1)" in output
        assert "LOW SEVERITY (1)" in output
        assert "a.py:10" in output
        assert "Suggestion: Fix it" in output

    def test_text_reports_no_issues(self):
        assert "No issues found" in format_text(ReviewResult())

    def test_text_warns_about_incomplete_runs(self):
        output = format_text(ReviewResult(failed_chunks=2))

        assert "incomplete" in output

    def test_json_round_trips(self):
        payload = json.loads(format_json(self.result()))

        assert payload["summary"]["total"] == 2
        assert payload["findings"][0]["line"] == 10

    def test_markdown_is_comment_ready(self):
        output = format_markdown(self.result())

        assert output.startswith("## ReviewMindBot")
        assert "**a.py:10**" in output
        assert "_Suggestion:_ Fix it" in output

    def test_unattributed_findings_are_labelled(self):
        output = format_text(
            ReviewResult(findings=[Finding(Severity.LOW, Category.BUG, "x")])
        )

        assert "(unattributed)" in output
