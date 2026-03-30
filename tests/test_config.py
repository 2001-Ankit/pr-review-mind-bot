import pytest

from app.config import Config, ConfigError


def test_validate_provider_api_key_uses_groq_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "groq-secret")
    config = Config()

    assert config.validate_provider_api_key("groq") == "groq-secret"


def test_invalid_chunk_overlap_raises(monkeypatch):
    monkeypatch.setenv("CHUNK_OVERLAP", "not-an-int")
    config = Config()

    with pytest.raises(ConfigError):
        _ = config.chunk_overlap


def test_github_token_is_optional(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    config = Config()

    assert config.github_token is None
