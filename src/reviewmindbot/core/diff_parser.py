"""Unified-diff parser.

Produces plain data objects; nothing here talks to a model or the network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class Hunk:
    """A single ``@@`` block within a file's diff."""

    header: str
    raw_lines: list[str] = field(default_factory=list)
    added_lines: list[str] = field(default_factory=list)
    removed_lines: list[str] = field(default_factory=list)
    context_lines: list[str] = field(default_factory=list)
    #: 1-based line number of the first line of this hunk in the new file.
    new_start: int = 0
    #: New-file line numbers of the added lines, positionally aligned with
    #: ``added_lines``. GitHub rejects review comments on lines outside the
    #: diff, so posting inline requires knowing exactly which lines are valid.
    added_line_numbers: list[int] = field(default_factory=list)

    def to_text(self) -> str:
        """The hunk as it appeared in the diff, header included."""
        return "\n".join([self.header, *self.raw_lines])

    def annotated_added_lines(self) -> list[tuple[int, str]]:
        """Added lines paired with their new-file line numbers."""
        return list(zip(self.added_line_numbers, self.added_lines, strict=False))


@dataclass
class FileChange:
    """All hunks belonging to one file path."""

    file_name: str
    hunks: list[Hunk] = field(default_factory=list)
    total_added: int = 0
    total_removed: int = 0
    is_deleted: bool = False
    is_new: bool = False
    is_binary: bool = False

    @property
    def total_changes(self) -> int:
        return self.total_added + self.total_removed

    def commentable_lines(self) -> set[int]:
        """New-file line numbers an inline review comment may target."""
        return {
            line_number
            for hunk in self.hunks
            for line_number in hunk.added_line_numbers
        }


class DiffParser:
    """Parses ``git diff`` output into :class:`FileChange` objects."""

    def parse(self, diff: str) -> list[FileChange]:
        files: list[FileChange] = []
        current_file: FileChange | None = None
        current_hunk: Hunk | None = None
        new_line_no = 0

        for line in diff.splitlines():
            if line.startswith("diff --git"):
                if current_file is not None:
                    files.append(current_file)
                current_file = FileChange(file_name=self._file_name(line))
                current_hunk = None
                continue

            if current_file is None:
                continue

            if line.startswith("new file mode"):
                current_file.is_new = True
            elif line.startswith("deleted file mode"):
                current_file.is_deleted = True
            elif line.startswith("Binary files ") or line.startswith("GIT binary patch"):
                current_file.is_binary = True
            elif line.startswith("@@"):
                current_hunk = Hunk(header=line, new_start=self._new_start(line))
                current_file.hunks.append(current_hunk)
                new_line_no = current_hunk.new_start
            elif current_hunk is not None:
                new_line_no = self._consume_hunk_line(
                    current_file, current_hunk, line, new_line_no
                )

        if current_file is not None:
            files.append(current_file)

        return files

    @staticmethod
    def _consume_hunk_line(
        file: FileChange, hunk: Hunk, line: str, new_line_no: int
    ) -> int:
        """Record one hunk line and return the next new-file line number.

        Added and context lines advance the new-file counter; removed lines do
        not exist in the new file and so do not.
        """
        # "\ No newline at end of file" is a marker, not content.
        if line.startswith("\\"):
            return new_line_no

        hunk.raw_lines.append(line)

        # No `+++`/`---` guard is needed: those file headers always precede the
        # first `@@`, so inside a hunk a leading `+++` is real added content
        # (e.g. `++i;` in C). Guarding on it silently dropped such lines.
        if line.startswith("+"):
            hunk.added_lines.append(line[1:])
            hunk.added_line_numbers.append(new_line_no)
            file.total_added += 1
            return new_line_no + 1

        if line.startswith("-"):
            hunk.removed_lines.append(line[1:])
            file.total_removed += 1
            return new_line_no

        if line.startswith(" "):
            hunk.context_lines.append(line[1:])

        return new_line_no + 1

    @staticmethod
    def _file_name(line: str) -> str:
        """Extract the post-image path from a ``diff --git`` line."""
        parts = line.split()
        b_path = parts[3] if len(parts) >= 4 else ""
        return b_path[2:] if b_path.startswith("b/") else b_path

    @staticmethod
    def _new_start(header: str) -> int:
        match = _HUNK_HEADER.match(header)
        return int(match.group(2)) if match else 0
