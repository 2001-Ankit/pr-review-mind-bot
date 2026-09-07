from conftest import StubLLM
from reviewmindbot.core.chunking import Chunk
from reviewmindbot.engine.reviewer import Reviewer


def review(response: str, files=("demo.py",)):
    return Reviewer(StubLLM(response)).review(Chunk(text="diff", files=list(files)))


def test_valid_findings_are_parsed():
    findings = review(
        """[
          {"severity": "HIGH", "category": "bug", "message": "Null check is missing",
           "file_name": "demo.py", "line": 12, "suggestion": "Guard against None"}
        ]"""
    )

    assert len(findings) == 1
    assert findings[0].severity == "high"
    assert findings[0].category == "bug"
    assert findings[0].file_name == "demo.py"
    assert findings[0].line == 12
    assert findings[0].suggestion == "Guard against None"


def test_invalid_severity_category_or_message_is_dropped():
    findings = review(
        """[
          {"severity": "critical", "category": "bug", "message": "bad severity"},
          {"severity": "low", "category": "typo", "message": "bad category"},
          {"severity": "medium", "category": "test", "message": ""}
        ]"""
    )

    assert findings == []


def test_markdown_fenced_json_is_still_parsed():
    """Models wrap JSON in fences constantly; discarding it loses real findings."""
    findings = review(
        '```json\n[{"severity": "low", "category": "style", "message": "Nit"}]\n```'
    )

    assert len(findings) == 1
    assert findings[0].message == "Nit"


def test_json_with_surrounding_prose_is_recovered():
    findings = review(
        'Here is the review:\n[{"severity": "high", "category": "security", '
        '"message": "Hardcoded secret"}]\nHope that helps.'
    )

    assert len(findings) == 1
    assert findings[0].category == "security"


def test_object_wrapper_is_unwrapped():
    findings = review(
        '{"findings": [{"severity": "low", "category": "refactor", "message": "Extract"}]}'
    )

    assert len(findings) == 1


def test_unparseable_response_yields_no_findings():
    assert review("I could not review this.") == []


def test_single_file_chunk_attributes_findings_automatically():
    """Without this the file_name was almost always null in the output."""
    findings = review(
        '[{"severity": "low", "category": "refactor", "message": "Extract helper"}]',
        files=("only.py",),
    )

    assert findings[0].file_name == "only.py"


def test_multi_file_chunk_leaves_unclaimed_findings_unattributed():
    findings = review(
        '[{"severity": "low", "category": "refactor", "message": "Extract helper"}]',
        files=("a.py", "b.py"),
    )

    assert findings[0].file_name is None


def test_model_reported_path_is_matched_against_the_chunk():
    findings = review(
        '[{"severity": "low", "category": "bug", "message": "x", "file_name": "mod.py"}]',
        files=("src/pkg/mod.py", "other.py"),
    )

    assert findings[0].file_name == "src/pkg/mod.py"


def test_bogus_line_numbers_are_discarded():
    findings = review(
        '[{"severity": "low", "category": "bug", "message": "x", "line": "not-a-line"}]'
    )

    assert findings[0].line is None
