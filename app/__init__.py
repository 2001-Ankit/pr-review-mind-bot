"""ReviewMindBot - Intelligent PR code review tool."""

__version__ = "0.1.0"

from app.config import Config, get_config, ConfigError

__all__ = ["Config", "get_config", "ConfigError"]
