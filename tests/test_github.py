from unittest.mock import Mock, patch

import pytest
import requests

from reviewmindbot.errors import DiffSourceError
from reviewmindbot.integration.github import (
    COMMENT_MARKER,
    GitHubClient,
    GitHubError,
    PullRequest,
    fetch_pr_diff,
    is_pr_url,
    parse_pr_url,
)

PR = PullRequest("org", "repo", 1)


@pytest.fixture
def client():
    return GitHubClient(token="t")


def response(status=200, text="", json_data=None):
    mock = Mock(status_code=status, text=text)
    mock.json.return_value = json_data if json_data is not None else {}
    return mock


class TestUrlParsing:
    def test_extracts_components(self):
        assert parse_pr_url("https://github.com/org/repo/pull/12") == ("org", "repo", 12)
        assert parse_pr_url("https://github.com/org/repo/pull/12/") == ("org", "repo", 12)

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.example.com/org/repo/pull/1",
            "https://github.com/org/repo/issues/1",
            "not a url",
            "https://github.com/org/repo",
        ],
    )
    def test_rejects_non_github_pr_urls(self, url):
        """Any string used to be suffixed with '.diff' and fetched with the token."""
        with pytest.raises(DiffSourceError):
            parse_pr_url(url)

    def test_is_pr_url(self):
        assert is_pr_url("https://github.com/o/r/pull/1") is True
        assert is_pr_url("changes.diff") is False


class TestFetchDiff:
    def test_uses_the_api_with_the_diff_media_type(self, client):
        with patch.object(client._session, "request") as request:
            request.return_value = response(200, "diff data")

            assert client.fetch_diff(PR) == "diff data"

        method, url = request.call_args[0]
        headers = request.call_args[1]["headers"]
        assert method == "GET"
        assert url == "https://api.github.com/repos/org/repo/pulls/1"
        assert headers["Accept"] == "application/vnd.github.v3.diff"
        assert headers["Authorization"] == "Bearer t"

    def test_no_authorization_header_without_a_token(self):
        anonymous = GitHubClient()
        with patch.object(anonymous._session, "request") as request:
            request.return_value = response(200, "diff")
            anonymous.fetch_diff(PR)

        assert "Authorization" not in request.call_args[1]["headers"]

    def test_404_explains_the_private_repo_case(self, client):
        with patch.object(client._session, "request", return_value=response(404)):
            with pytest.raises(DiffSourceError, match="GITHUB_TOKEN"):
                client.fetch_diff(PR)

    def test_403_mentions_the_rate_limit(self, client):
        with patch.object(client._session, "request", return_value=response(403)):
            with pytest.raises(DiffSourceError, match="rate limit"):
                client.fetch_diff(PR)

    def test_empty_diff_is_an_error(self, client):
        with patch.object(client._session, "request", return_value=response(200, "  ")):
            with pytest.raises(DiffSourceError, match="empty diff"):
                client.fetch_diff(PR)

    def test_network_failure_is_wrapped(self, client):
        with patch.object(
            client._session, "request", side_effect=requests.ConnectionError("offline")
        ):
            with pytest.raises(DiffSourceError, match="Could not reach GitHub"):
                client.fetch_diff(PR)

    def test_module_level_helper_still_works(self):
        with patch.object(requests.Session, "request", return_value=response(200, "d")):
            assert fetch_pr_diff("https://github.com/org/repo/pull/1") == "d"


class TestSummaryComment:
    def test_creates_a_comment_when_none_exists(self, client):
        with patch.object(client._session, "request") as request:
            request.side_effect = [
                response(200, json_data=[]),  # find_bot_comment
                response(201),  # create
            ]

            assert client.upsert_summary_comment(PR, "hello") == "created"

        method, url = request.call_args[0]
        assert method == "POST"
        assert url.endswith("/issues/1/comments")

    def test_updates_the_previous_comment_in_place(self, client):
        """A bot that appends on every push buries the PR discussion."""
        with patch.object(client._session, "request") as request:
            request.side_effect = [
                response(200, json_data=[{"id": 99, "body": f"{COMMENT_MARKER} old"}]),
                response(200),
            ]

            assert client.upsert_summary_comment(PR, "new body") == "updated"

        method, url = request.call_args[0]
        assert method == "PATCH"
        assert url.endswith("/issues/comments/99")

    def test_ignores_comments_from_other_authors(self, client):
        with patch.object(client._session, "request") as request:
            request.side_effect = [
                response(200, json_data=[{"id": 5, "body": "a human said this"}]),
                response(201),
            ]

            assert client.upsert_summary_comment(PR, "body") == "created"

    def test_marker_is_embedded_in_the_body(self, client):
        with patch.object(client._session, "request") as request:
            request.side_effect = [response(200, json_data=[]), response(201)]
            client.upsert_summary_comment(PR, "visible text")

        assert COMMENT_MARKER in request.call_args[1]["json"]["body"]

    def test_failure_is_reported(self, client):
        with patch.object(client._session, "request") as request:
            request.side_effect = [
                response(200, json_data=[]),
                response(403, json_data={"message": "Resource not accessible"}),
            ]

            with pytest.raises(GitHubError, match="Resource not accessible"):
                client.upsert_summary_comment(PR, "body")


class TestReviewComments:
    def test_posts_comments_as_one_review(self, client):
        comments = [{"path": "a.py", "line": 3, "side": "RIGHT", "body": "x"}]
        with patch.object(client._session, "request", return_value=response(201)):
            assert client.post_review_comments(PR, comments, commit_sha="abc") == 1

    def test_nothing_to_post_makes_no_request(self, client):
        with patch.object(client._session, "request") as request:
            assert client.post_review_comments(PR, []) == 0
            request.assert_not_called()

    def test_rejected_positions_degrade_instead_of_failing(self, client):
        """A 422 must not fail the build; the summary still carries the findings."""
        comments = [{"path": "a.py", "line": 9999, "side": "RIGHT", "body": "x"}]
        rejected = response(422, json_data={"message": "Invalid request"})

        with patch.object(client._session, "request", return_value=rejected):
            assert client.post_review_comments(PR, comments) == 0

    def test_other_errors_are_raised(self, client):
        comments = [{"path": "a.py", "line": 3, "side": "RIGHT", "body": "x"}]
        with patch.object(
            client._session, "request", return_value=response(500, json_data={"message": "boom"})
        ):
            with pytest.raises(GitHubError):
                client.post_review_comments(PR, comments)
