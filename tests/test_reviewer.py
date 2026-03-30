from app.engine.reviewer import Reviewer


class StubLLM:
    def __init__(self, response):
        self.response = response

    def generate(self, system_prompt, user_prompt):
        return self.response


def test_review_chunk_filters_invalid_items():
    reviewer = Reviewer(
        StubLLM(
            """
            [
              {"severity": "HIGH", "category": "bug", "message": "Null check is missing"},
              {"severity": "critical", "category": "bug", "message": "bad severity"},
              {"severity": "low", "category": "typo", "message": "bad category"},
              {"severity": "medium", "category": "test", "message": ""}
            ]
            """
        )
    )

    findings = reviewer.review_chunk("some diff")

    assert len(findings) == 1
    assert findings[0].severity == "high"
    assert findings[0].category == "bug"
    assert findings[0].message == "Null check is missing"


def test_review_chunk_returns_empty_on_invalid_json():
    reviewer = Reviewer(StubLLM("not-json"))

    assert reviewer.review_chunk("some diff") == []


def test_review_file_uses_hunks_as_context():
    reviewer = Reviewer(
        StubLLM('[{"severity": "low", "category": "refactor", "message": "Extract helper"}]')
    )

    class Hunk:
        raw_lines = ["+value = 1"]

    class FileChange:
        file_name = "demo.py"
        hunks = [Hunk()]

    findings = reviewer.review_file(FileChange())

    assert len(findings) == 1
    assert findings[0].category == "refactor"
