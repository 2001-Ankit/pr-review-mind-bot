"""Decides which files are worth sending to the model."""

from __future__ import annotations

import fnmatch

from ..core.diff_parser import FileChange

#: Paths that cost tokens and yield nothing useful in review.
DEFAULT_IGNORE_PATTERNS = (
    "*.lock",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.svg",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.pdf",
    "*.woff*",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "Cargo.lock",
    "go.sum",
    "*/migrations/*",
    "*.snap",
)


class FileRouter:
    """Filters the parsed diff before any tokens are spent."""

    def __init__(
        self,
        ignore_patterns: tuple[str, ...] = DEFAULT_IGNORE_PATTERNS,
        skip_deleted: bool = True,
    ) -> None:
        self.ignore_patterns = ignore_patterns
        self.skip_deleted = skip_deleted

    def should_review(self, file: FileChange) -> bool:
        if file.is_binary or not file.hunks:
            return False
        # A deleted file has no new code to critique.
        if self.skip_deleted and file.is_deleted:
            return False
        return not self.is_ignored(file.file_name)

    def is_ignored(self, file_name: str) -> bool:
        return any(
            fnmatch.fnmatch(file_name, pattern) for pattern in self.ignore_patterns
        )

    def select(self, files: list[FileChange]) -> list[FileChange]:
        return [f for f in files if self.should_review(f)]
