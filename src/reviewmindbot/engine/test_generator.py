"""Generates unit tests for newly added code."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..core.diff_parser import FileChange
from ..errors import ProviderError
from ..llm.base import LLMProvider
from .prompts import TEST_SYSTEM_PROMPT, TEST_USER_PROMPT

logger = logging.getLogger(__name__)

_EMPTY_MARKER = "# no tests needed"


@dataclass(frozen=True)
class GeneratedTests:
    file_name: str
    code: str


class TestGenerator:
    # Keep pytest from collecting this class as a test suite.
    __test__ = False

    def __init__(self, llm: LLMProvider, *, min_added_lines: int = 3) -> None:
        self.llm = llm
        self.min_added_lines = min_added_lines

    def generate(self, files: list[FileChange]) -> list[GeneratedTests]:
        """One request per file, not per hunk.

        Per-hunk generation produced disconnected fragments and multiplied cost;
        a file's added lines are the unit that can actually be tested together.
        """
        results: list[GeneratedTests] = []

        for file in files:
            added = [line for hunk in file.hunks for line in hunk.added_lines]
            if len(added) < self.min_added_lines:
                continue

            try:
                response = self.llm.generate(
                    TEST_SYSTEM_PROMPT,
                    TEST_USER_PROMPT.format(
                        file_name=file.file_name, code="\n".join(added)
                    ),
                )
            except ProviderError as exc:
                logger.error("Test generation failed for %s: %s", file.file_name, exc)
                continue

            code = _strip_fences(response)
            if code and _EMPTY_MARKER not in code.lower():
                results.append(GeneratedTests(file_name=file.file_name, code=code))

        return results


def _strip_fences(text: str) -> str:
    lines = (text or "").strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
