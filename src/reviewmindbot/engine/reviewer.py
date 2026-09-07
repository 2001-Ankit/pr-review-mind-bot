"""Turns a diff chunk into structured findings."""

from __future__ import annotations

import json
import logging
import re

from ..cache import NullCache, ResponseCache, make_key
from ..core.chunking import Chunk
from ..llm.base import LLMProvider
from ..usage import Budget
from .models import Category, Finding, Severity
from .prompts import REVIEW_SYSTEM_PROMPT, REVIEW_USER_PROMPT

logger = logging.getLogger(__name__)

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_ARRAY = re.compile(r"\[.*\]", re.DOTALL)


class Reviewer:
    """Reviews one chunk at a time. Stateless between calls."""

    def __init__(
        self,
        llm: LLMProvider,
        *,
        cache: ResponseCache | None = None,
        budget: Budget | None = None,
    ) -> None:
        self.llm = llm
        self.cache = cache or NullCache()
        self.budget = budget

    def review(self, chunk: Chunk) -> list[Finding]:
        user_prompt = REVIEW_USER_PROMPT.format(chunk=chunk.text)
        key = make_key(self.llm.name, self.llm.model, REVIEW_SYSTEM_PROMPT, user_prompt)

        cached = self.cache.get(key)
        if cached is not None:
            logger.debug("Cache hit for chunk covering %s", ", ".join(chunk.files))
            self.llm.usage.record_cache_hit()
            return self._parse(cached, known_files=chunk.files)

        # Checked before the request, so a budget is a limit rather than a
        # post-mortem on what was already spent.
        if self.budget is not None:
            self.budget.check(self.llm.usage, REVIEW_SYSTEM_PROMPT + user_prompt)

        response = self.llm.generate(REVIEW_SYSTEM_PROMPT, user_prompt)
        self.cache.set(key, response)
        return self._parse(response, known_files=chunk.files)

    def _parse(self, response: str, known_files: list[str]) -> list[Finding]:
        data = _extract_json_array(response)
        if data is None:
            logger.warning("Discarding unparseable model response: %.200s", response)
            return []

        findings = []
        for item in data:
            finding = _build_finding(item, known_files)
            if finding is not None:
                findings.append(finding)
        return findings


def _extract_json_array(response: str) -> list | None:
    """Pull a JSON array out of a model response.

    Models wrap JSON in ``` fences or add a sentence of preamble often enough
    that treating that as "no findings" -- as the previous version did -- threw
    away real results.
    """
    if not response:
        return None

    text = _FENCE.sub("", response.strip())

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = _ARRAY.search(text)
        if match is None:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    # Tolerate {"findings": [...]} as well as a bare array.
    if isinstance(data, dict):
        for key in ("findings", "issues", "results"):
            if isinstance(data.get(key), list):
                return data[key]
        return None

    return data if isinstance(data, list) else None


def _build_finding(item: object, known_files: list[str]) -> Finding | None:
    if not isinstance(item, dict):
        return None

    message = str(item.get("message", "")).strip()
    if not message:
        return None

    try:
        severity = Severity(str(item.get("severity", "")).strip().lower())
        category = Category(str(item.get("category", "")).strip().lower())
    except ValueError:
        logger.debug("Dropping finding with unknown severity/category: %s", item)
        return None

    file_name = _resolve_file_name(item.get("file_name"), known_files)
    suggestion = item.get("suggestion")

    return Finding(
        severity=severity,
        category=category,
        message=message,
        file_name=file_name,
        line=_coerce_line(item.get("line")),
        suggestion=str(suggestion).strip() if suggestion else None,
    )


def _resolve_file_name(raw: object, known_files: list[str]) -> str | None:
    """Trust the model's path only if it matches a file actually in the chunk.

    When the chunk covers a single file, fall back to that file so findings are
    always attributable -- previously ``file_name`` was almost always null.
    """
    if isinstance(raw, str) and raw.strip():
        candidate = raw.strip()
        if candidate in known_files:
            return candidate
        for known in known_files:
            if known.endswith(candidate) or candidate.endswith(known):
                return known

    return known_files[0] if len(known_files) == 1 else None


def _coerce_line(raw: object) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw > 0 else None
    if isinstance(raw, str) and raw.strip().isdigit():
        value = int(raw.strip())
        return value if value > 0 else None
    return None
