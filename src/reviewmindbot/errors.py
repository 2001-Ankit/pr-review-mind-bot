"""Exception hierarchy.

Every error the tool raises on purpose derives from :class:`ReviewMindBotError`,
so the CLI can render a clean message instead of a traceback while still letting
genuinely unexpected exceptions surface.
"""


class ReviewMindBotError(Exception):
    """Base class for all expected failures."""


class ConfigError(ReviewMindBotError):
    """Raised when configuration is missing or invalid."""


class ProviderError(ReviewMindBotError):
    """Raised when an LLM provider is unknown or fails to answer."""


class DiffSourceError(ReviewMindBotError):
    """Raised when a diff cannot be read or fetched."""
