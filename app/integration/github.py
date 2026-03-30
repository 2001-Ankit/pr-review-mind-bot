import requests


def fetch_pr_diff(pr_url: str, github_token: str = None, timeout: int = 30) -> str:
    """Convert a PR URL to a .diff URL and download it."""
    if not pr_url.endswith(".diff"):
        pr_url = pr_url.rstrip("/") + ".diff"

    headers = {}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    response = requests.get(pr_url, headers=headers, timeout=timeout)

    if response.status_code != 200:
        raise Exception(
            f"Failed to fetch PR diff ({response.status_code}): {response.text[:200]}"
        )

    return response.text
