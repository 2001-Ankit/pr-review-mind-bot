"""Combines per-chunk findings into a single ordered, de-duplicated list."""

from __future__ import annotations

from collections.abc import Iterable

from .models import Finding


class Aggregator:
    def aggregate(self, batches: Iterable[Iterable[Finding]]) -> list[Finding]:
        """Flatten, drop duplicates, and sort by severity.

        Overlapping chunks legitimately produce the same finding twice, so
        de-duplication is required rather than cosmetic.
        """
        seen: set[tuple] = set()
        unique: list[Finding] = []

        for batch in batches:
            for finding in batch:
                key = finding.dedup_key()
                if key in seen:
                    continue
                seen.add(key)
                unique.append(finding)

        unique.sort(
            key=lambda f: (-f.severity.rank, f.file_name or "", f.line or 0)
        )
        return unique
