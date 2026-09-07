"""On-disk response cache.

Re-running a review on an unchanged PR is the common case: a workflow re-run, a
push that touches one file out of thirty, a flaky job retried. Without a cache
every one of those pays full price for identical work.

Keys cover the provider, model, prompt and the tool's own review contract, so a
prompt change or a model switch cannot serve a stale answer.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

#: Bumped whenever the review contract changes in a way that invalidates
#: previously cached responses (prompt wording, finding schema, parser rules).
CACHE_SCHEMA_VERSION = 1

DEFAULT_TTL_SECONDS = 14 * 24 * 60 * 60  # 14 days


def default_cache_path() -> Path:
    """Per-user cache location, following platform conventions."""
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "reviewmindbot" / "cache.db"


def make_key(provider: str, model: str, system_prompt: str, user_prompt: str) -> str:
    payload = "\x00".join(
        [str(CACHE_SCHEMA_VERSION), provider, model, system_prompt, user_prompt]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResponseCache:
    """SQLite-backed cache of raw model responses.

    Every operation is best-effort: a corrupt, locked or unwritable cache
    degrades to a cache miss rather than failing the review.
    """

    def __init__(
        self,
        path: Path | None = None,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        enabled: bool = True,
    ) -> None:
        self.path = Path(path) if path else default_cache_path()
        self.ttl_seconds = ttl_seconds
        self.enabled = enabled
        self._lock = threading.Lock()
        self._connection: sqlite3.Connection | None = None
        if self.enabled:
            self._connect()

    def _connect(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                self.path, check_same_thread=False, timeout=5.0
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS responses (
                    key        TEXT PRIMARY KEY,
                    response   TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            connection.commit()
            self._connection = connection
        except (OSError, sqlite3.Error) as exc:
            logger.debug("Cache unavailable (%s); continuing without it", exc)
            self.enabled = False
            self._connection = None

    def get(self, key: str) -> str | None:
        if not self.enabled or self._connection is None:
            return None

        cutoff = time.time() - self.ttl_seconds
        try:
            with self._lock:
                row = self._connection.execute(
                    "SELECT response FROM responses WHERE key = ? AND created_at > ?",
                    (key, cutoff),
                ).fetchone()
        except sqlite3.Error as exc:
            logger.debug("Cache read failed (%s)", exc)
            return None

        return row[0] if row else None

    def set(self, key: str, response: str) -> None:
        if not self.enabled or self._connection is None:
            return
        try:
            with self._lock:
                self._connection.execute(
                    "INSERT OR REPLACE INTO responses VALUES (?, ?, ?)",
                    (key, response, time.time()),
                )
                self._connection.commit()
        except sqlite3.Error as exc:
            logger.debug("Cache write failed (%s)", exc)

    def purge_expired(self) -> int:
        """Drop entries past their TTL. Returns the number removed."""
        if not self.enabled or self._connection is None:
            return 0
        try:
            with self._lock:
                cursor = self._connection.execute(
                    "DELETE FROM responses WHERE created_at <= ?",
                    (time.time() - self.ttl_seconds,),
                )
                self._connection.commit()
                return cursor.rowcount
        except sqlite3.Error:
            return 0

    def clear(self) -> None:
        if self._connection is None:
            return
        try:
            with self._lock:
                self._connection.execute("DELETE FROM responses")
                self._connection.commit()
        except sqlite3.Error:
            pass

    def stats(self) -> dict:
        if not self.enabled or self._connection is None:
            return {"enabled": False, "entries": 0}
        try:
            with self._lock:
                (count,) = self._connection.execute(
                    "SELECT COUNT(*) FROM responses"
                ).fetchone()
        except sqlite3.Error:
            count = 0
        return {"enabled": True, "entries": count, "path": str(self.path)}

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except sqlite3.Error:
                pass
            self._connection = None

    def __enter__(self) -> ResponseCache:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


class NullCache(ResponseCache):
    """Explicitly disabled cache, for ``--no-cache`` and tests."""

    def __init__(self) -> None:
        super().__init__(path=Path("unused"), enabled=False)


def diff_fingerprint(diff_text: str) -> str:
    """Stable identifier for a diff, useful for logging and sticky comments."""
    return hashlib.sha256(diff_text.encode("utf-8")).hexdigest()[:12]


__all__ = [
    "CACHE_SCHEMA_VERSION",
    "NullCache",
    "ResponseCache",
    "default_cache_path",
    "diff_fingerprint",
    "make_key",
]
