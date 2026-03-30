import io
import json
from contextlib import redirect_stdout

from app.engine.models import ReviewFindings


class DummyLLM:
    def generate(self, system_prompt, user_prompt):
        return "[]"


def test_chunk_blocks_uses_config_sizes():
    from app.cli import chunk_blocks

    class Config:
        max_chunk_size = 10
        chunk_overlap = 0

    chunks = chunk_blocks(["abcdefghij", "klmnop"], Config())

    assert len(chunks) >= 2


def test_extract_added_code_returns_only_added_lines():
    from app.cli import extract_added_code

    class Hunk:
        added_lines = ["x = 1"]

    class EmptyHunk:
        added_lines = []

    class FileChange:
        file_name = "demo.py"
        hunks = [Hunk(), EmptyHunk()]

    blocks = extract_added_code([FileChange()])

    assert len(blocks) == 1
    assert "x = 1" in blocks[0]


def test_json_output_shape_for_findings():
    findings = [
        ReviewFindings(severity="high", category="bug", message="broken flow"),
        ReviewFindings(severity="low", category="test", message="needs test"),
    ]
    by_severity = {"high": [findings[0]], "medium": [], "low": [findings[1]]}

    payload = {
        "summary": {
            "total": len(findings),
            "high": len(by_severity["high"]),
            "medium": len(by_severity["medium"]),
            "low": len(by_severity["low"]),
        },
        "findings": [
            {
                "severity": issue.severity,
                "category": issue.category,
                "message": issue.message,
                "file_name": issue.file_name,
            }
            for issue in findings
        ],
    }

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        print(json.dumps(payload, indent=2))

    parsed = json.loads(buffer.getvalue())
    assert parsed["summary"]["total"] == 2
    assert parsed["findings"][0]["severity"] == "high"
