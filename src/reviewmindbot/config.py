"""Environment-driven configuration.

Config is resolved once, eagerly, into an immutable object. The previous
implementation exposed lazy properties that re-read ``os.environ`` on every
access and raised from inside a getter, which made validation order impossible
to reason about and let providers bypass config entirely.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from .errors import ConfigError

DEFAULT_PROVIDER = "gemini"

#: Environment variables consulted for each provider's credential, in order.
#: The first non-empty value wins. Multiple names are accepted where the
#: ecosystem is genuinely split (Google's SDK reads ``GOOGLE_API_KEY``, but
#: every doc and dashboard calls it a "Gemini API key").
PROVIDER_KEY_ENV_VARS: Mapping[str, tuple[str, ...]] = {
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openai": ("OPENAI_API_KEY",),
    "groq": ("GROQ_API_KEY",),
}

#: Where to get a key, shown when one is missing.
PROVIDER_KEY_URLS: Mapping[str, str] = {
    "gemini": "https://aistudio.google.com/apikey",
    "openai": "https://platform.openai.com/api-keys",
    "groq": "https://console.groq.com/keys",
}

#: Default model per provider, overridable via ``REVIEWMINDBOT_MODEL``.
DEFAULT_MODELS: Mapping[str, str] = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "groq": "llama-3.3-70b-versatile",
}

SUPPORTED_PROVIDERS: tuple[str, ...] = tuple(PROVIDER_KEY_ENV_VARS)


def _default_log_file() -> Path:
    """Log under the user's state directory, never the current directory.

    An installed CLI must not drop ``reviewmindbot.log`` into whatever repo the
    user happens to be standing in, and must not crash when that directory is
    read-only.
    """
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "reviewmindbot" / "reviewmindbot.log"


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from None
    if value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}, got {value}")
    return value


@dataclass(frozen=True)
class Config:
    """Resolved, validated configuration."""

    provider: str = DEFAULT_PROVIDER
    model: str | None = None
    log_level: str = "INFO"
    log_file: Path = field(default_factory=_default_log_file)
    max_chunk_size: int = 12000
    chunk_overlap: int = 400
    max_concurrency: int = 4
    request_timeout: int = 60
    max_retries: int = 3
    github_token: str | None = None
    #: Hard spend ceiling for one run, in USD. None means unlimited.
    budget_usd: float | None = None
    cache_enabled: bool = True
    cache_ttl_seconds: int = 14 * 24 * 60 * 60

    def resolve_model(self, provider: str) -> str:
        """Model to use for ``provider``, honouring an explicit override."""
        return self.model or DEFAULT_MODELS.get(provider, "")

    def api_key_for(self, provider: str) -> str:
        """Return the credential for ``provider`` or explain how to get one."""
        provider = provider.lower()
        env_vars = PROVIDER_KEY_ENV_VARS.get(provider)
        if env_vars is None:
            raise ConfigError(
                f"Unknown provider: {provider}. "
                f"Supported: {', '.join(SUPPORTED_PROVIDERS)}"
            )

        for name in env_vars:
            value = os.getenv(name)
            if value:
                return value

        names = " or ".join(env_vars)
        raise ConfigError(
            f"{names} not set. Export it or add it to a .env file.\n"
            f"Get a key at: {PROVIDER_KEY_URLS.get(provider, '')}"
        )


def load_dotenv_file(start: Path | None = None) -> None:
    """Load a ``.env`` from the working directory or any parent of it.

    Only the user's own tree is searched. The old implementation fell back to
    the package's parent directory, which after ``pip install`` is
    ``site-packages`` -- never a meaningful place to look.
    """
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            load_dotenv(candidate)
            return


def load_config(*, load_env: bool = True) -> Config:
    """Build a :class:`Config` from the environment."""
    if load_env:
        load_dotenv_file()

    provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER).strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ConfigError(
            f"Invalid LLM_PROVIDER: {provider}. "
            f"Supported: {', '.join(SUPPORTED_PROVIDERS)}"
        )

    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError(f"Invalid LOG_LEVEL: {log_level}")

    log_file_env = os.getenv("LOG_FILE")
    chunk_overlap = _env_int("CHUNK_OVERLAP", 400)
    max_chunk_size = _env_int("MAX_CHUNK_SIZE", 12000, minimum=1)
    if chunk_overlap >= max_chunk_size:
        raise ConfigError(
            f"CHUNK_OVERLAP ({chunk_overlap}) must be smaller than "
            f"MAX_CHUNK_SIZE ({max_chunk_size})"
        )

    model = os.getenv("REVIEWMINDBOT_MODEL") or None

    return Config(
        provider=provider,
        model=model,
        log_level=log_level,
        log_file=Path(log_file_env) if log_file_env else _default_log_file(),
        max_chunk_size=max_chunk_size,
        chunk_overlap=chunk_overlap,
        max_concurrency=_env_int("MAX_CONCURRENCY", 4, minimum=1),
        request_timeout=_env_int("REQUEST_TIMEOUT", 60, minimum=1),
        max_retries=_env_int("MAX_RETRIES", 3, minimum=1),
        github_token=os.getenv("GITHUB_TOKEN") or None,
        budget_usd=_env_float("BUDGET_USD"),
        cache_enabled=_env_bool("CACHE_ENABLED", default=True),
        cache_ttl_seconds=_env_int("CACHE_TTL_SECONDS", 14 * 24 * 60 * 60, minimum=0),
    )


def _env_float(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from None
    if value <= 0:
        raise ConfigError(f"{name} must be greater than 0, got {value}")
    return value


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}
