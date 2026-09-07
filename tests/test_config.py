import pytest

from reviewmindbot.config import Config, load_config
from reviewmindbot.errors import ConfigError


def test_gemini_key_is_accepted_under_either_name(monkeypatch):
    """The docs and the dashboard say GEMINI_API_KEY; the SDK says GOOGLE_API_KEY.

    v0.1.0 read only GOOGLE_API_KEY while telling users to set GEMINI_API_KEY,
    which made the published package unusable as documented.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "from-gemini-var")
    assert Config().api_key_for("gemini") == "from-gemini-var"

    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setenv("GOOGLE_API_KEY", "from-google-var")
    assert Config().api_key_for("gemini") == "from-google-var"


def test_missing_key_names_every_accepted_variable(monkeypatch):
    with pytest.raises(ConfigError) as exc:
        Config().api_key_for("gemini")

    assert "GEMINI_API_KEY" in str(exc.value)
    assert "GOOGLE_API_KEY" in str(exc.value)


@pytest.mark.parametrize(
    ("provider", "env_var"),
    [("openai", "OPENAI_API_KEY"), ("groq", "GROQ_API_KEY")],
)
def test_provider_keys(monkeypatch, provider, env_var):
    monkeypatch.setenv(env_var, "secret")

    assert Config().api_key_for(provider) == "secret"


def test_unknown_provider_is_rejected():
    with pytest.raises(ConfigError):
        Config().api_key_for("hal9000")


def test_invalid_provider_env_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "skynet")

    with pytest.raises(ConfigError, match="Invalid LLM_PROVIDER"):
        load_config(load_env=False)


def test_non_integer_chunk_setting_is_rejected(monkeypatch):
    monkeypatch.setenv("CHUNK_OVERLAP", "not-an-int")

    with pytest.raises(ConfigError, match="CHUNK_OVERLAP"):
        load_config(load_env=False)


def test_overlap_larger_than_chunk_is_rejected(monkeypatch):
    monkeypatch.setenv("MAX_CHUNK_SIZE", "100")
    monkeypatch.setenv("CHUNK_OVERLAP", "200")

    with pytest.raises(ConfigError, match="must be smaller"):
        load_config(load_env=False)


def test_github_token_is_optional():
    assert load_config(load_env=False).github_token is None


def test_log_file_defaults_outside_the_working_directory(tmp_path, monkeypatch):
    """An installed CLI must not litter the user's repo with a log file."""
    monkeypatch.chdir(tmp_path)

    config = load_config(load_env=False)

    assert config.log_file.parent != tmp_path
    assert config.log_file.name == "reviewmindbot.log"


def test_model_override(monkeypatch):
    monkeypatch.setenv("REVIEWMINDBOT_MODEL", "some-model")

    assert load_config(load_env=False).resolve_model("gemini") == "some-model"


def test_default_model_per_provider():
    config = load_config(load_env=False)

    assert config.resolve_model("gemini")
    assert config.resolve_model("openai") != config.resolve_model("gemini")


def test_dotenv_is_found_in_a_parent_directory(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("GROQ_API_KEY=from-dotenv\n", encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    assert load_config().api_key_for("groq") == "from-dotenv"
