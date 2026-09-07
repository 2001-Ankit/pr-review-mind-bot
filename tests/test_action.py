"""The action.yml contract.

The Action is the primary way people will use this, and it is the one part of
the project that cannot be exercised by importing it. These tests at least keep
its declared interface honest against the CLI it drives.
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ACTION = Path(__file__).resolve().parents[1] / "action.yml"


@pytest.fixture(scope="module")
def action():
    return yaml.safe_load(ACTION.read_text(encoding="utf-8"))


def test_action_file_exists_and_parses(action):
    assert action["name"]
    assert action["runs"]["using"] == "composite"


def test_declares_the_inputs_users_need(action):
    expected = {
        "provider",
        "model",
        "api-key",
        "github-token",
        "comment",
        "inline",
        "fail-on",
        "budget-usd",
    }

    assert expected <= set(action["inputs"])


def test_api_key_is_required_and_has_no_default(action):
    """A default API key would be a credential baked into the repo."""
    api_key = action["inputs"]["api-key"]

    assert api_key["required"] is True
    assert "default" not in api_key


def test_provider_default_matches_the_library_default(action):
    from reviewmindbot.config import DEFAULT_PROVIDER

    assert action["inputs"]["provider"]["default"] == DEFAULT_PROVIDER


def test_every_provider_has_a_key_env_var_wired_in(action):
    """Adding a provider without wiring its key here would silently fail."""
    from reviewmindbot.config import PROVIDER_KEY_ENV_VARS

    review_step = next(
        step for step in action["runs"]["steps"] if step.get("id") == "review"
    )
    env = review_step["env"]

    for provider, names in PROVIDER_KEY_ENV_VARS.items():
        assert any(name in env for name in names), f"{provider} key is not passed through"


def test_fail_on_choices_match_the_cli(action):
    from reviewmindbot.cli import _FAIL_ON_RANK

    described = action["inputs"]["fail-on"]["description"]
    for choice in _FAIL_ON_RANK:
        assert choice in described


def test_budget_defaults_to_a_real_limit(action):
    """An unlimited default would let one large PR run up an unbounded bill."""
    default = action["inputs"]["budget-usd"]["default"]

    assert float(default) > 0


def test_outputs_are_declared(action):
    assert {"total", "high", "cost-usd", "result-json"} <= set(action["outputs"])


def test_default_github_token_is_the_workflow_token(action):
    assert "github.token" in action["inputs"]["github-token"]["default"]


def test_dogfooding_workflow_grants_write_permission():
    workflow_path = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pr-review.yml"
    )
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    assert workflow["permissions"]["pull-requests"] == "write"
