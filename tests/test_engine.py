import pytest

from conftest import StubLLM
from reviewmindbot.core.diff_parser import DiffParser, FileChange, Hunk
from reviewmindbot.engine.aggregator import Aggregator
from reviewmindbot.engine.file_router import FileRouter
from reviewmindbot.engine.models import Category, Finding, ReviewResult, Severity
from reviewmindbot.engine.orchestrator import Orchestrator
from reviewmindbot.engine.reviewer import Reviewer
from reviewmindbot.engine.test_generator import TestGenerator
from reviewmindbot.errors import ProviderError
from reviewmindbot.llm.base import Completion


def finding(severity="low", message="msg", file_name="a.py", category="bug"):
    return Finding(
        severity=Severity(severity),
        category=Category(category),
        message=message,
        file_name=file_name,
    )


class TestAggregator:
    def test_sorts_by_severity_descending(self):
        result = Aggregator().aggregate(
            [[finding("low", "l")], [finding("high", "h")], [finding("medium", "m")]]
        )

        assert [f.severity for f in result] == ["high", "medium", "low"]

    def test_duplicates_from_overlapping_chunks_are_collapsed(self):
        duplicate = finding("high", "Same problem")
        result = Aggregator().aggregate([[duplicate], [duplicate], [finding("low", "Other")]])

        assert len(result) == 2

    def test_same_message_in_different_files_is_kept(self):
        result = Aggregator().aggregate(
            [[finding("low", "Same", "a.py")], [finding("low", "Same", "b.py")]]
        )

        assert len(result) == 2


class TestFileRouter:
    @pytest.mark.parametrize(
        "name", ["package-lock.json", "uv.lock", "bundle.min.js", "logo.png"]
    )
    def test_noise_files_are_skipped(self, name):
        file = FileChange(file_name=name, hunks=[Hunk(header="@@")])

        assert FileRouter().should_review(file) is False

    def test_source_files_are_reviewed(self):
        file = FileChange(file_name="src/app.py", hunks=[Hunk(header="@@")])

        assert FileRouter().should_review(file) is True

    def test_deleted_and_binary_files_are_skipped(self):
        deleted = FileChange(file_name="gone.py", hunks=[Hunk(header="@@")], is_deleted=True)
        binary = FileChange(file_name="a.bin", hunks=[Hunk(header="@@")], is_binary=True)

        assert FileRouter().should_review(deleted) is False
        assert FileRouter().should_review(binary) is False

    def test_select_filters_a_batch(self):
        files = [
            FileChange(file_name="src/app.py", hunks=[Hunk(header="@@")]),
            FileChange(file_name="uv.lock", hunks=[Hunk(header="@@")]),
        ]

        assert [f.file_name for f in FileRouter().select(files)] == ["src/app.py"]


class TestOrchestrator:
    def build(self, llm, **kwargs):
        return Orchestrator(Reviewer(llm), max_concurrency=1, **kwargs)

    def parsed(self):
        return DiffParser().parse(
            "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1,2 @@\n+x = 1\n+y = 2\n"
        )

    def test_end_to_end_produces_a_result(self):
        llm = StubLLM('[{"severity": "high", "category": "bug", "message": "Boom"}]')

        result = self.build(llm).review(self.parsed())

        assert len(result.findings) == 1
        assert result.files_reviewed == 1
        assert result.chunks_reviewed == 1
        assert result.failed_chunks == 0

    def test_ignored_files_never_reach_the_model(self):
        llm = StubLLM("[]")
        files = DiffParser().parse(
            "diff --git a/uv.lock b/uv.lock\n--- a/uv.lock\n+++ b/uv.lock\n@@ -1 +1 @@\n+x\n"
        )

        result = self.build(llm).review(files)

        assert llm.calls == []
        assert result.files_reviewed == 0

    def test_a_failing_chunk_does_not_lose_the_others(self):
        """One provider error used to abort the entire run."""
        files = DiffParser().parse(
            "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1,2 @@\n"
            + "\n".join(f"+line_{i} = {i}" for i in range(30))
            + "\n"
        )

        class FlakyLLM(StubLLM):
            def _complete(self, system_prompt, user_prompt):
                self.calls.append((system_prompt, user_prompt))
                if len(self.calls) == 1:
                    raise RuntimeError("boom")
                return Completion(
                    text='[{"severity": "low", "category": "bug", "message": "ok"}]',
                    input_tokens=10,
                    output_tokens=5,
                )

        orchestrator = self.build(FlakyLLM(), max_chunk_size=200, chunk_overlap=0)
        result = orchestrator.review(files)

        assert result.failed_chunks == 1
        assert len(result.findings) >= 1

    def test_total_provider_failure_is_raised(self):
        llm = StubLLM(fail_with=RuntimeError("no key"))

        with pytest.raises(ProviderError):
            self.build(llm).review(self.parsed())

    def test_empty_diff_yields_an_empty_result(self):
        result = self.build(StubLLM()).review([])

        assert result.findings == []
        assert result.chunks_reviewed == 0


class TestTestGenerator:
    def make_file(self, added):
        return FileChange(file_name="a.py", hunks=[Hunk(header="@@", added_lines=added)])

    def test_one_request_per_file(self):
        llm = StubLLM("def test_x():\n    assert True")
        files = [self.make_file(["def x(): ...", "y = 1", "z = 2"])]

        suites = TestGenerator(llm).generate(files)

        assert len(llm.calls) == 1
        assert len(suites) == 1
        assert suites[0].file_name == "a.py"

    def test_trivial_changes_are_skipped(self):
        llm = StubLLM("whatever")

        assert TestGenerator(llm).generate([self.make_file(["x = 1"])]) == []
        assert llm.calls == []

    def test_fences_are_stripped(self):
        llm = StubLLM("```python\ndef test_x():\n    assert True\n```")

        suites = TestGenerator(llm).generate([self.make_file(["a", "b", "c"])])

        assert suites[0].code.startswith("def test_x")

    def test_no_tests_needed_marker_produces_nothing(self):
        llm = StubLLM("# no tests needed")

        assert TestGenerator(llm).generate([self.make_file(["a", "b", "c"])]) == []


class TestReviewResult:
    def test_summary_shape(self):
        result = ReviewResult(
            findings=[finding("high"), finding("low", "other")],
            files_reviewed=2,
            chunks_reviewed=3,
        )

        payload = result.to_dict()

        assert payload["summary"]["total"] == 2
        assert payload["summary"]["high"] == 1
        assert payload["summary"]["files_reviewed"] == 2
        assert payload["findings"][0]["severity"] == "high"
