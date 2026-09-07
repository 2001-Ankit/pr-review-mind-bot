"""Domain objects for review results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def rank(self) -> int:
        return {"high": 3, "medium": 2, "low": 1}[self.value]


class Category(StrEnum):
    BUG = "bug"
    SECURITY = "security"
    REFACTOR = "refactor"
    TEST = "test"
    PERFORMANCE = "performance"
    STYLE = "style"


@dataclass(frozen=True)
class Finding:
    """One issue reported by the model."""

    severity: Severity
    category: Category
    message: str
    file_name: str | None = None
    line: int | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict:
        return {
            "severity": str(self.severity),
            "category": str(self.category),
            "message": self.message,
            "file_name": self.file_name,
            "line": self.line,
            "suggestion": self.suggestion,
        }

    def dedup_key(self) -> tuple:
        """Identity used to collapse the same issue seen in overlapping chunks."""
        return (self.file_name, str(self.category), self.message.strip().lower())


@dataclass
class ReviewResult:
    """Everything a run produced."""

    findings: list[Finding] = field(default_factory=list)
    files_reviewed: int = 0
    chunks_reviewed: int = 0
    #: Chunks whose review call failed outright; the run continues without them.
    failed_chunks: int = 0
    #: Chunks never sent because the budget ran out.
    skipped_chunks: int = 0
    budget_exhausted: bool = False
    #: Token and cost totals, as produced by :meth:`Usage.to_dict`.
    usage: dict = field(default_factory=dict)

    def by_severity(self, severity: Severity) -> list[Finding]:
        return [f for f in self.findings if f.severity is severity]

    @property
    def counts(self) -> dict[str, int]:
        return {s.value: len(self.by_severity(s)) for s in Severity}

    @property
    def complete(self) -> bool:
        """False when some of the diff was never actually reviewed."""
        return not self.failed_chunks and not self.skipped_chunks

    def to_dict(self) -> dict:
        return {
            "summary": {
                "total": len(self.findings),
                **self.counts,
                "files_reviewed": self.files_reviewed,
                "chunks_reviewed": self.chunks_reviewed,
                "failed_chunks": self.failed_chunks,
                "skipped_chunks": self.skipped_chunks,
                "budget_exhausted": self.budget_exhausted,
                "complete": self.complete,
            },
            "usage": self.usage,
            "findings": [f.to_dict() for f in self.findings],
        }
