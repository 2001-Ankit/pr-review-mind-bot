"""Renders a :class:`ReviewResult` for humans and machines.

Formatting lives here rather than inline in ``main()``, where the "no findings"
and "has findings" paths each built their own JSON payload and header block.
"""

from __future__ import annotations

import json

from ..engine.models import Finding, ReviewResult, Severity

_SEVERITY_LABEL = {
    Severity.HIGH: "HIGH",
    Severity.MEDIUM: "MEDIUM",
    Severity.LOW: "LOW",
}


def format_json(result: ReviewResult) -> str:
    return json.dumps(result.to_dict(), indent=2)


def format_text(result: ReviewResult) -> str:
    lines = ["", "=" * 60, "REVIEW RESULTS", "=" * 60, ""]

    if not result.findings:
        lines.append(
            "No issues found."
            if result.complete
            else "No issues found in the parts that were reviewed."
        )
    else:
        for severity in Severity:
            findings = result.by_severity(severity)
            if not findings:
                continue
            lines.append(f"{_SEVERITY_LABEL[severity]} SEVERITY ({len(findings)})")
            for finding in findings:
                lines.extend(_format_finding(finding))
            lines.append("")

    counts = result.counts
    lines.append(
        f"Summary: {len(result.findings)} issue(s) across "
        f"{result.files_reviewed} file(s) - "
        f"high: {counts['high']}, medium: {counts['medium']}, low: {counts['low']}"
    )

    usage_line = _usage_line(result)
    if usage_line:
        lines.append(usage_line)

    if result.budget_exhausted:
        lines.append(
            f"Warning: budget reached - {result.skipped_chunks} chunk(s) were "
            "never reviewed. Raise --budget-usd for full coverage."
        )
    if result.failed_chunks:
        lines.append(
            f"Warning: {result.failed_chunks} chunk(s) could not be reviewed; "
            "results are incomplete."
        )

    return "\n".join(lines)


def _usage_line(result: ReviewResult) -> str:
    usage = result.usage or {}
    if not usage.get("requests") and not usage.get("cached_requests"):
        return ""

    parts = [f"{usage.get('requests', 0)} request(s)"]
    if usage.get("cached_requests"):
        parts.append(f"{usage['cached_requests']} from cache")
    if usage.get("total_tokens"):
        parts.append(f"{usage['total_tokens']:,} tokens")
    if usage.get("cost_usd"):
        parts.append(f"~${usage['cost_usd']:.4f}")

    return f"Cost:    {', '.join(parts)}"


def format_markdown(result: ReviewResult) -> str:
    """GitHub-comment-ready output."""
    counts = result.counts
    lines = ["## ReviewMindBot", ""]

    if result.findings:
        lines.append(
            f"Found **{len(result.findings)}** issue(s) - "
            f"{counts['high']} high, {counts['medium']} medium, {counts['low']} low."
        )
    elif result.complete:
        lines.append("No issues found in the reviewed changes.")
    else:
        # "No issues found" on a run that never finished would be a lie, and
        # the most damaging kind: it reads as a clean bill of health.
        lines.append("No issues found in the parts that were reviewed.")
    lines.append("")

    for severity in Severity:
        findings = result.by_severity(severity)
        if not findings:
            continue
        lines.append(f"### {_SEVERITY_LABEL[severity]}")
        lines.append("")
        for finding in findings:
            lines.append(f"- **{_location(finding)}** ({finding.category}) {finding.message}")
            if finding.suggestion:
                lines.append(f"  - _Suggestion:_ {finding.suggestion}")
        lines.append("")

    if not result.complete:
        caveats = []
        if result.budget_exhausted:
            caveats.append(f"budget reached, {result.skipped_chunks} chunk(s) skipped")
        if result.failed_chunks:
            caveats.append(f"{result.failed_chunks} chunk(s) failed")
        lines.append(f"> ⚠️ Partial review — {'; '.join(caveats)}.")

    return "\n".join(lines)


def _format_finding(finding: Finding) -> list[str]:
    lines = [f"  - [{finding.category}] {_location(finding)}", f"    {finding.message}"]
    if finding.suggestion:
        lines.append(f"    Suggestion: {finding.suggestion}")
    return lines


def _location(finding: Finding) -> str:
    if finding.file_name and finding.line:
        return f"{finding.file_name}:{finding.line}"
    return finding.file_name or "(unattributed)"


FORMATTERS = {
    "text": format_text,
    "json": format_json,
    "markdown": format_markdown,
}
