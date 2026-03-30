from unittest.mock import Mock, patch

import pytest

from app.integration.github import fetch_pr_diff


@patch("app.integration.github.requests.get")
def test_fetch_pr_diff_adds_diff_suffix_and_auth_header(mock_get):
    response = Mock(status_code=200, text="diff data")
    mock_get.return_value = response

    result = fetch_pr_diff(
        "https://github.com/org/repo/pull/1",
        github_token="token-123",
        timeout=15,
    )

    assert result == "diff data"
    mock_get.assert_called_once_with(
        "https://github.com/org/repo/pull/1.diff",
        headers={"Authorization": "Bearer token-123"},
        timeout=15,
    )


@patch("app.integration.github.requests.get")
def test_fetch_pr_diff_raises_with_status_details(mock_get):
    response = Mock(status_code=404, text="not found")
    mock_get.return_value = response

    with pytest.raises(Exception, match="404"):
        fetch_pr_diff("https://github.com/org/repo/pull/1")
