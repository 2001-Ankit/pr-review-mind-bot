"""Publishes a :class:`ReviewResult` to a pull request.

Kept separate from the HTTP client: deciding *what* to say and *where* it can
legally go is review logic, not transport.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..core.diff_parser import FileChange
from ..engine.models import Finding, ReviewResult, Severity
from ..reporting.formatters import format_markdown
from .github import GitHubClient, PullRequest

logger = logging.getLogger(__name__)

#: GitHub refuses a review with too many comments and reviewers stop reading
#: long before the API does.
MAX_INLINE_COMMENTS = 30

_SEVERITY_EMOJI = {
    Severity.HIGH: "🔴",
    Severity.MEDIUM: "🟠",
    Severity.LOW: "🔵",
}


@dataclass
class PublishOutcome:
    summary_action: str | None = None
    inline_posted: int = 0
    inline_skipped: int = 0

    def describe(self) -> str:
        parts = []
        if self.summary_action:
            parts.append(f"summary comment {self.summary_action}")
        if self.inline_posted:
            parts.append(f"{self.inline_posted} inline comment(s) posted")
        if self.inline_skipped:
            parts.append(f"{self.inline_skipped} not attachable to a diff line")
        return ", ".join(parts) or "nothing to publish"


def commentable_lines(files: list[FileChange]) -> dict[str, set[int]]:
    """New-file line numbers per path that a review comment may target."""
    return {file.file_name: file.commentable_lines() for file in files}


def build_inline_comments(
    findings: list[Finding],
    line_index: dict[str, set[int]],
    limit: int = MAX_INLINE_COMMENTS,
) -> tuple[list[dict], list[Finding]]:
    """Split findings into postable inline comments and the leftovers.

    GitHub rejects the whole review if any single comment names a line outside
    the diff, so anything unverifiable is deliberately left for the summary.
    """
    comments: list[dict] = []
    leftover: list[Finding] = []

    for finding in findings:
        if len(comments) >= limit:
            leftover.append(finding)
            continue

        valid_lines = line_index.get(finding.file_name or "")
        if not finding.file_name or not finding.line or not valid_lines:
            leftover.append(finding)
            continue

        if finding.line not in valid_lines:
            logger.debug(
                "Line %s of %s is not in the diff; keeping it in the summary",
                finding.line,
                finding.file_name,
            )
            leftover.append(finding)
            continue

        comments.append(
            {
                "path": finding.file_name,
                "line": finding.line,
                "side": "RIGHT",
                "body": format_inline_body(finding),
            }
        )

    return comments, leftover


def format_inline_body(finding: Finding) -> str:
    emoji = _SEVERITY_EMOJI.get(finding.severity, "")
    lines = [
        f"{emoji} **{str(finding.severity).upper()} · {finding.category}**",
        "",
        finding.message,
    ]
    if finding.suggestion:
        lines += ["", f"**Suggestion:** {finding.suggestion}"]
    return "\n".join(lines)


def build_summary(result: ReviewResult, leftover: list[Finding]) -> str:
    """Summary comment body: headline, caveats, then anything not inlined."""
    counts = result.counts
    lines: list[str] = []

    if result.findings:
        lines.append(
            f"### ReviewMindBot — {len(result.findings)} issue(s): "
            f"🔴 {counts['high']} high · 🟠 {counts['medium']} medium · "
            f"🔵 {counts['low']} low"
        )
    elif result.complete:
        lines.append("### ✅ ReviewMindBot — no issues found")
    else:
        # A green check on a run that never finished is the most damaging
        # thing this bot could post: it reads as a clean bill of health.
        lines.append("### ⚠️ ReviewMindBot — no issues found in the parts reviewed")

    lines.append("")

    if not result.complete:
        caveats = []
        if result.budget_exhausted:
            caveats.append(
                f"the cost budget was reached, so {result.skipped_chunks} "
                "part(s) of this diff were not reviewed"
            )
        if result.failed_chunks:
            caveats.append(f"{result.failed_chunks} part(s) failed to review")
        lines += [f"> ⚠️ **Partial review** — {'; '.join(caveats)}.", ""]

    if leftover:
        if len(leftover) < len(result.findings):
            lines.append("#### Findings not attached to a specific line")
        lines.append("")
        for finding in leftover:
            emoji = _SEVERITY_EMOJI.get(finding.severity, "")
            location = finding.file_name or "(unattributed)"
            if finding.line:
                location = f"{location}:{finding.line}"
            lines.append(
                f"- {emoji} **{location}** ({finding.category}) {finding.message}"
            )
            if finding.suggestion:
                lines.append(f"  - _Suggestion:_ {finding.suggestion}")
        lines.append("")

    lines.append(_footer(result))
    return "\n".join(lines)


def _footer(result: ReviewResult) -> str:
    usage = result.usage or {}
    bits = [f"{result.files_reviewed} file(s) reviewed"]

    if usage.get("total_tokens"):
        bits.append(f"{usage['total_tokens']:,} tokens")
    if usage.get("cost_usd"):
        bits.append(f"~${usage['cost_usd']:.4f}")
    if usage.get("cached_requests"):
        bits.append(f"{usage['cached_requests']} cached")
    if usage.get("model"):
        bits.append(usage["model"])

    return f"<sub>🤖 ReviewMindBot · {' · '.join(bits)}</sub>"


def publish_review(
    client: GitHubClient,
    pr: PullRequest,
    result: ReviewResult,
    files: list[FileChange],
    *,
    inline: bool = True,
    summary: bool = True,
    limit: int = MAX_INLINE_COMMENTS,
) -> PublishOutcome:
    """Post a review result to a pull request."""
    outcome = PublishOutcome()
    leftover = result.findings

    if inline and result.findings:
        comments, leftover = build_inline_comments(
            result.findings, commentable_lines(files), limit
        )
        if comments:
            commit_sha = client.head_sha(pr)
            posted = client.post_review_comments(pr, comments, commit_sha=commit_sha)
            outcome.inline_posted = posted
            if posted == 0:
                # The review was rejected: nothing was inlined, so every
                # finding has to survive in the summary.
                leftover = result.findings
        outcome.inline_skipped = len(leftover)

    if summary:
        outcome.summary_action = client.upsert_summary_comment(
            pr, build_summary(result, leftover)
        )

    return outcome


__all__ = [
    "MAX_INLINE_COMMENTS",
    "PublishOutcome",
    "build_inline_comments",
    "build_summary",
    "commentable_lines",
    "format_markdown",
    "publish_review",
]
