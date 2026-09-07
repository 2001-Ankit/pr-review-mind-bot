"""Diff parsing and chunking - no LLM knowledge lives here."""

from .chunking import Chunk, build_chunks
from .diff_parser import DiffParser, FileChange, Hunk

__all__ = ["Chunk", "build_chunks", "DiffParser", "FileChange", "Hunk"]
