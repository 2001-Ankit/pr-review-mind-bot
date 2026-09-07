"""GitHub integration: fetch PR diffs and post review feedback."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

from ..errors import DiffSourceError, ReviewMindBotError

logger = logging.getLogger(__name__)

#: https://github.com/<owner>/<repo>/pull/<number>
_PR_URL = re.compile(
    r"^https?://(?P<host>[^/]+)/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)/?$"
)

_ALLOWED_HOSTS = {"github.com", "www.github.com"}

API_ROOT = "https://api.github.com"

#: Marks the bot's own summary comment so repeat runs update it in place
#: instead of adding a new comment to every push.
COMMENT_MARKER = "<!-- reviewmindbot:summary -->"


class GitHubError(ReviewMindBotError):
    """Raised when a GitHub write operation fails."""


@dataclass(frozen=True)
class PullRequest:
    owner: str
    repo: str
    number: int

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}#{self.number}"


def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    """Validate a PR URL and return ``(owner, repo, number)``.

    The old implementation appended ``.diff`` to any string it was handed and
    fetched it, which meant a typo or a hostile argument became an arbitrary
    outbound request carrying the user's GitHub token.
    """
    match = _PR_URL.match(pr_url.strip())
    if match is None:
        raise DiffSourceError(
            f"Not a GitHub pull request URL: {pr_url}\n"
            "Expected: https://github.com/<owner>/<repo>/pull/<number>"
        )

    host = match.group("host").lower()
    if host not in _ALLOWED_HOSTS:
        raise DiffSourceError(f"Unsupported host: {host}. Only github.com is supported.")

    return match.group("owner"), match.group("repo"), int(match.group("number"))


def parse_pull_request(pr_url: str) -> PullRequest:
    return PullRequest(*parse_pr_url(pr_url))


def is_pr_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and "/pull/" in parsed.path


class GitHubClient:
    """Thin GitHub REST client covering exactly what a review bot needs."""

    def __init__(self, token: str | None = None, timeout: int = 30) -> None:
        self.token = token
        self.timeout = timeout
        self._session = requests.Session()

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = path if path.startswith("http") else f"{API_ROOT}{path}"
        try:
            return self._session.request(
                method, url, timeout=self.timeout, **kwargs
            )
        except requests.RequestException as exc:
            raise DiffSourceError(f"Could not reach GitHub: {exc}") from exc

    # -- reading -------------------------------------------------------

    def fetch_diff(self, pr: PullRequest) -> str:
        response = self._request(
            "GET",
            f"/repos/{pr.owner}/{pr.repo}/pulls/{pr.number}",
            headers=self._headers("application/vnd.github.v3.diff"),
        )

        if response.status_code == 404:
            raise DiffSourceError(
                f"PR not found: {pr.slug}. "
                "If the repository is private, set GITHUB_TOKEN."
            )
        if response.status_code in (401, 403):
            detail = "rate limit or permissions"
            if not self.token:
                detail += " - set GITHUB_TOKEN to raise the limit"
            raise DiffSourceError(f"GitHub refused the request ({detail}).")
        if response.status_code != 200:
            raise DiffSourceError(
                f"GitHub returned {response.status_code}: {response.text[:200]}"
            )
        if not response.text.strip():
            raise DiffSourceError(f"PR {pr.slug} has an empty diff.")

        return response.text

    def head_sha(self, pr: PullRequest) -> str | None:
        """Commit the review applies to; inline comments must name it."""
        response = self._request(
            "GET",
            f"/repos/{pr.owner}/{pr.repo}/pulls/{pr.number}",
            headers=self._headers(),
        )
        if response.status_code != 200:
            return None
        return (response.json().get("head") or {}).get("sha")

    def find_bot_comment(self, pr: PullRequest) -> int | None:
        """Locate a previous summary comment by its hidden marker."""
        response = self._request(
            "GET",
            f"/repos/{pr.owner}/{pr.repo}/issues/{pr.number}/comments",
            headers=self._headers(),
            params={"per_page": 100},
        )
        if response.status_code != 200:
            return None

        for comment in response.json():
            if COMMENT_MARKER in (comment.get("body") or ""):
                return comment.get("id")
        return None

    # -- writing -------------------------------------------------------

    def upsert_summary_comment(self, pr: PullRequest, body: str) -> str:
        """Post the summary, replacing the bot's previous one if present.

        A bot that appends a fresh comment on every push buries the discussion
        it is supposed to support, so the summary is edited in place.
        """
        body = f"{COMMENT_MARKER}\n{body}"
        existing = self.find_bot_comment(pr)

        if existing is not None:
            response = self._request(
                "PATCH",
                f"/repos/{pr.owner}/{pr.repo}/issues/comments/{existing}",
                headers=self._headers(),
                json={"body": body},
            )
            action = "updated"
        else:
            response = self._request(
                "POST",
                f"/repos/{pr.owner}/{pr.repo}/issues/{pr.number}/comments",
                headers=self._headers(),
                json={"body": body},
            )
            action = "created"

        if response.status_code not in (200, 201):
            raise GitHubError(
                f"Could not post the summary comment ({response.status_code}): "
                f"{_error_detail(response)}"
            )

        return action

    def post_review_comments(
        self,
        pr: PullRequest,
        comments: list[dict],
        *,
        commit_sha: str | None = None,
        body: str = "",
    ) -> int:
        """Post inline comments as a single PR review.

        Returns the number of comments posted. Falls back to a review with no
        inline comments if GitHub rejects the positions, so a line-mapping
        problem downgrades the output instead of failing the run.
        """
        if not comments:
            return 0

        payload: dict = {"event": "COMMENT", "comments": comments}
        if body:
            payload["body"] = body
        if commit_sha:
            payload["commit_id"] = commit_sha

        response = self._request(
            "POST",
            f"/repos/{pr.owner}/{pr.repo}/pulls/{pr.number}/reviews",
            headers=self._headers(),
            json=payload,
        )

        if response.status_code in (200, 201):
            return len(comments)

        if response.status_code == 422:
            logger.warning(
                "GitHub rejected the inline positions (%s); "
                "findings remain in the summary comment.",
                _error_detail(response),
            )
            return 0

        raise GitHubError(
            f"Could not post review comments ({response.status_code}): "
            f"{_error_detail(response)}"
        )


def _error_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]

    message = payload.get("message", "")
    errors = payload.get("errors")
    if errors:
        message = f"{message}: {errors}"
    return str(message)[:300]


def fetch_pr_diff(
    pr_url: str,
    github_token: str | None = None,
    timeout: int = 30,
) -> str:
    """Download the unified diff for a GitHub pull request."""
    return GitHubClient(github_token, timeout).fetch_diff(parse_pull_request(pr_url))
