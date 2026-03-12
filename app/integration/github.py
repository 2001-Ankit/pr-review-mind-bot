import requests


def fetch_pr_diff(pr_url: str, github_token: str = None) -> str:
    """
    Convert PR URL to .diff URL and download it
    """

    if not pr_url.endswith(".diff"):
        pr_url = pr_url.rstrip("/") + ".diff"

    response = requests.get(pr_url)

    if response.status_code != 200:
        raise Exception("Failed to fetch PR diff")

    return response.text