from unittest.mock import Mock

import pytest

from reviewmindbot.core.diff_parser import DiffParser
from reviewmindbot.engine.models import Category, Finding, ReviewResult, Severity
from reviewmindbot.integration.github import PullRequest
from reviewmindbot.integration.publisher import (
    build_inline_comments,
    build_summary,
    commentable_lines,
    publish_review,
)

PR = PullRequest("org", "repo", 1)

DIFF = """diff --git a/app.py b/app.py
index 1111111..2222222 100644
--- a/app.py
+++ b/app.py
@@ -10,3 +10,5 @@ def existing():
 context_line
-removed = 1
+added_one = 1
+added_two = 2
 trailing_context
"""


def finding(severity="high", file_name="app.py", line=12, suggestion=None):
    return Finding(
        severity=Severity(severity),
        category=Category.BUG,
        message="Something is wrong",
        file_name=file_name,
        line=line,
        suggestion=suggestion,
    )


@pytest.fixture
def files():
    return DiffParser().parse(DIFF)


class TestLineMapping:
    def test_added_lines_get_new_file_line_numbers(self, files):
        hunk = files[0].hunks[0]

        # Hunk starts at new-file line 10: context 10, removed (no number),
        # added 11 and 12, trailing context 13.
        assert hunk.added_line_numbers == [11, 12]
        assert hunk.annotated_added_lines() == [(11, "added_one = 1"), (12, "added_two = 2")]

    def test_commentable_lines_are_the_added_lines(self, files):
        assert commentable_lines(files) == {"app.py": {11, 12}}


class TestInlineComments:
    def test_finding_on_an_added_line_becomes_a_comment(self, files):
        comments, leftover = build_inline_comments([finding(line=12)], commentable_lines(files))

        assert leftover == []
        assert comments == [
            {
                "path": "app.py",
                "line": 12,
                "side": "RIGHT",
                "body": comments[0]["body"],
            }
        ]
        assert "HIGH" in comments[0]["body"]

    def test_finding_on_a_context_line_stays_in_the_summary(self, files):
        """GitHub rejects the whole review if any comment is off-diff."""
        comments, leftover = build_inline_comments([finding(line=13)], commentable_lines(files))

        assert comments == []
        assert len(leftover) == 1

    def test_finding_without_a_line_stays_in_the_summary(self, files):
        comments, leftover = build_inline_comments([finding(line=None)], commentable_lines(files))

        assert comments == []
        assert len(leftover) == 1

    def test_finding_in_an_unknown_file_stays_in_the_summary(self, files):
        comments, leftover = build_inline_comments(
            [finding(file_name="ghost.py")], commentable_lines(files)
        )

        assert comments == []
        assert len(leftover) == 1

    def test_comment_count_is_capped(self, files):
        findings = [finding(line=11) for _ in range(50)]

        comments, leftover = build_inline_comments(findings, commentable_lines(files), limit=5)

        assert len(comments) == 5
        assert len(leftover) == 45

    def test_suggestion_is_included(self, files):
        comments, _ = build_inline_comments(
            [finding(line=11, suggestion="Do it differently")], commentable_lines(files)
        )

        assert "Do it differently" in comments[0]["body"]


class TestSummary:
    def test_clean_review_says_so(self):
        body = build_summary(ReviewResult(), [])

        assert "no issues found" in body.lower()

    def test_counts_are_headlined(self):
        result = ReviewResult(findings=[finding("high"), finding("low")])

        body = build_summary(result, [])

        assert "2 issue(s)" in body
        assert "1 high" in body

    def test_leftover_findings_are_listed(self):
        left = finding(line=None)
        body = build_summary(ReviewResult(findings=[left]), [left])

        assert "Something is wrong" in body

    def test_partial_review_is_flagged(self):
        """Silently reviewing half a PR would be worse than saying nothing."""
        result = ReviewResult(budget_exhausted=True, skipped_chunks=3)

        body = build_summary(result, [])

        assert "Partial review" in body
        assert "budget" in body

    def test_failed_chunks_are_flagged(self):
        body = build_summary(ReviewResult(failed_chunks=2), [])

        assert "Partial review" in body

    def test_footer_reports_usage(self):
        result = ReviewResult(
            files_reviewed=3,
            usage={"total_tokens": 1234, "cost_usd": 0.0123, "model": "gpt-4o-mini"},
        )

        body = build_summary(result, [])

        assert "3 file(s) reviewed" in body
        assert "1,234 tokens" in body
        assert "$0.0123" in body


class TestPublish:
    def client(self, inline_posted=1):
        client = Mock()
        client.head_sha.return_value = "abc123"
        client.post_review_comments.return_value = inline_posted
        client.upsert_summary_comment.return_value = "created"
        return client

    def test_posts_inline_comments_and_a_summary(self, files):
        client = self.client()

        outcome = publish_review(client, PR, ReviewResult(findings=[finding(line=11)]), files)

        assert outcome.inline_posted == 1
        assert outcome.summary_action == "created"
        client.post_review_comments.assert_called_once()
        client.upsert_summary_comment.assert_called_once()

    def test_inline_can_be_disabled(self, files):
        client = self.client()

        publish_review(client, PR, ReviewResult(findings=[finding(line=11)]), files, inline=False)

        client.post_review_comments.assert_not_called()
        client.upsert_summary_comment.assert_called_once()

    def test_rejected_review_falls_back_to_the_summary(self, files):
        """If GitHub refuses the inline positions, no finding may be lost."""
        client = self.client(inline_posted=0)
        result = ReviewResult(findings=[finding(line=11)])

        outcome = publish_review(client, PR, result, files)

        assert outcome.inline_posted == 0
        body = client.upsert_summary_comment.call_args[0][1]
        assert "Something is wrong" in body

    def test_clean_review_still_posts_a_summary(self, files):
        client = self.client()

        publish_review(client, PR, ReviewResult(), files)

        client.post_review_comments.assert_not_called()
        assert "no issues" in client.upsert_summary_comment.call_args[0][1].lower()

    def test_inline_comments_name_the_head_commit(self, files):
        client = self.client()

        publish_review(client, PR, ReviewResult(findings=[finding(line=11)]), files)

        assert client.post_review_comments.call_args[1]["commit_sha"] == "abc123"


class TestNoFalseCleanBill:
    """A run that never finished must not look like a passing review."""

    def test_incomplete_run_does_not_get_a_green_check(self):
        body = build_summary(ReviewResult(failed_chunks=2), [])

        assert "✅" not in body
        assert "Partial review" in body

    def test_complete_clean_run_does_get_a_green_check(self):
        body = build_summary(ReviewResult(files_reviewed=1), [])

        assert "✅" in body

    def test_budget_stopped_run_does_not_get_a_green_check(self):
        body = build_summary(
            ReviewResult(budget_exhausted=True, skipped_chunks=4), []
        )

        assert "✅" not in body
        assert "budget" in body
