"""Packs parsed hunks into model-sized chunks.

Two properties matter and were previously missing:

* A chunk remembers which files it came from, so findings can be attributed to
  a path even when the model does not name one.
* Splitting happens on hunk boundaries first and on line boundaries second.
  Character-slicing a diff mid-token destroys exactly the context the model
  needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .diff_parser import FileChange, Hunk

_SEPARATOR = "\n\n"


@dataclass
class Chunk:
    """A block of diff text plus the files it covers."""

    text: str
    files: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.text)


def render_hunk(file_name: str, hunk: Hunk) -> str:
    """Format one hunk for the model, with a new-file line-number gutter.

    The gutter costs a few tokens per line and buys accurate ``line`` values in
    the response, which is what makes inline PR comments land on the right
    line instead of being rejected. Removed lines get a blank gutter because
    they do not exist in the new file and cannot be commented on.
    """
    lines = [f"FILE: {file_name}", f"{'':>5} {hunk.header}"]
    line_no = hunk.new_start

    for raw in hunk.raw_lines:
        if raw.startswith("-"):
            lines.append(f"{'':>5} {raw}")
            continue
        lines.append(f"{line_no:>5} {raw}")
        line_no += 1

    return "\n".join(lines)


def build_chunks(
    files: list[FileChange],
    max_chunk_size: int,
    chunk_overlap: int = 0,
) -> list[Chunk]:
    """Group hunks into chunks of at most ``max_chunk_size`` characters."""
    if max_chunk_size <= 0:
        raise ValueError("max_chunk_size must be positive")

    chunks: list[Chunk] = []
    pending: list[str] = []
    pending_files: list[str] = []
    pending_size = 0

    def flush() -> None:
        nonlocal pending, pending_files, pending_size
        if not pending:
            return
        chunks.append(Chunk(text=_SEPARATOR.join(pending), files=list(pending_files)))
        pending = []
        pending_files = []
        pending_size = 0

    for file in files:
        if file.is_binary or not file.hunks:
            continue

        for hunk in file.hunks:
            block = render_hunk(file.file_name, hunk)

            if len(block) > max_chunk_size:
                # One hunk is bigger than a whole chunk: emit what we have,
                # then split this hunk on line boundaries.
                flush()
                for piece in _split_on_lines(block, max_chunk_size, chunk_overlap):
                    chunks.append(Chunk(text=piece, files=[file.file_name]))
                continue

            separator = len(_SEPARATOR) if pending else 0
            if pending_size + separator + len(block) > max_chunk_size:
                flush()
                separator = 0

            pending.append(block)
            pending_size += separator + len(block)
            if file.file_name not in pending_files:
                pending_files.append(file.file_name)

    flush()
    return chunks


def _split_on_lines(text: str, max_size: int, overlap: int) -> list[str]:
    """Split ``text`` into <= ``max_size`` pieces, never mid-line."""
    lines = text.splitlines()
    pieces: list[str] = []
    current: list[str] = []
    current_size = 0

    for line in lines:
        # A single line longer than max_size is the one case where we have no
        # choice but to cut inside it.
        if len(line) > max_size:
            if current:
                pieces.append("\n".join(current))
                current, current_size = [], 0
            pieces.extend(line[i : i + max_size] for i in range(0, len(line), max_size))
            continue

        separator = 1 if current else 0
        if current_size + separator + len(line) > max_size:
            pieces.append("\n".join(current))
            current = _overlap_lines(current, overlap)
            current_size = sum(len(item) + 1 for item in current)
            separator = 1 if current else 0

        current.append(line)
        current_size += separator + len(line)

    if current:
        pieces.append("\n".join(current))

    return pieces


def _overlap_lines(lines: list[str], overlap: int) -> list[str]:
    """Trailing lines of the previous piece to repeat, up to ``overlap`` chars."""
    if overlap <= 0:
        return []

    selected: list[str] = []
    size = 0
    for line in reversed(lines):
        if selected and size + len(line) > overlap:
            break
        selected.insert(0, line)
        size += len(line) + 1
        if size >= overlap:
            break
    return selected
