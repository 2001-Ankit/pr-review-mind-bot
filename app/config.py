import os
import sys
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when configuration is invalid."""
    pass


class Config:
    """Manages application configuration from environment variables."""
    
    SUPPORTED_PROVIDERS = ["gemini", "openai", "groq"]
    
    def __init__(self):
        """Initialize config and load environment variables."""
        self._load_env_file()
        self._validate_config()
    
    @staticmethod
    def _load_env_file():
        """Load environment variables from .env file if it exists."""
        env_path = Path.cwd() / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            # Try project root
            project_root = Path(__file__).parent.parent
            env_path = project_root / ".env"
            if env_path.exists():
                load_dotenv(env_path)
    
    def _validate_config(self):
        """Validate that required configuration is present."""
        # LLM provider validation happens on-demand
        pass
    
    @property
    def llm_provider(self) -> Literal["gemini", "openai", "groq"]:
        """Get the configured LLM provider (default: gemini)."""
        provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        if provider not in self.SUPPORTED_PROVIDERS:
            raise ConfigError(
                f"Invalid LLM_PROVIDER: {provider}. "
                f"Supported: {', '.join(self.SUPPORTED_PROVIDERS)}"
            )
        return provider
    
    @property
    def gemini_api_key(self) -> str:
        """Get Gemini API key."""
        key = os.getenv("GOOGLE_API_KEY")
        if not key:
            raise ConfigError(
                "GEMINI_API_KEY not found. Set it in .env file or as environment variable.\n"
                "Get your key at: https://ai.google.dev/gemini-api"
            )
        return key
    
    @property
    def openai_api_key(self) -> str:
        """Get OpenAI API key."""
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ConfigError(
                "OPENAI_API_KEY not found. Set it in .env file or as environment variable.\n"
                "Get your key at: https://platform.openai.com/api-keys"
            )
        return key
    @property
    def groq_api_key(self) -> str:
        """Get Groq API key."""
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise ConfigError(
                "GROQ_API_KEY not found. Set it in .env file or as environment variable.\n"
                "Get your key at: https://console.groq.com/keys"
            )
        return key

    @property
    def log_level(self) -> str:
        """Get logging level (default: INFO)."""
        return os.getenv("LOG_LEVEL", "INFO").upper()
    
    @property
    def log_file(self) -> str:
        """Get log file path (default: reviewmindbot.log)."""
        return os.getenv("LOG_FILE", "reviewmindbot.log")
    
    @property
    def max_chunk_size(self) -> int:
        """Get maximum chunk size for diff splitting (default: 500)."""
        try:
            return int(os.getenv("MAX_CHUNK_SIZE", "500"))
        except ValueError:
            raise ConfigError("MAX_CHUNK_SIZE must be an integer")
    
    @property
    def chunk_overlap(self) -> int:
        """Get chunk overlap size (default: 50)."""
        try:
            return int(os.getenv("CHUNK_OVERLAP", "50"))
        except ValueError:
            raise ConfigError("CHUNK_OVERLAP must be an integer")

    @property
    def github_token(self) -> str | None:
        """Get optional GitHub token for private PR access and rate limits."""
        return os.getenv("GITHUB_TOKEN")
    
    def validate_provider_api_key(self, provider: str) -> str:
        """Validate and return API key for the given provider."""
        provider = provider.lower()
        if provider == "gemini":
            return self.gemini_api_key
        elif provider == "openai":
            return self.openai_api_key
        elif provider == "groq":
            return self.groq_api_key
        else:
            raise ConfigError(f"Unknown provider: {provider}")
    
    def print_config(self):
        """Print current configuration (safe - no API keys)."""
        print(f"LLM Provider: {self.llm_provider}")
        print(f"Log Level: {self.log_level}")
        print(f"Log File: {self.log_file}")
        print(f"Max Chunk Size: {self.max_chunk_size}")
        print(f"Chunk Overlap: {self.chunk_overlap}")


def get_config() -> Config:
    """Get or create the global config instance."""
    if not hasattr(get_config, '_instance'):
        get_config._instance = Config()
    return get_config._instance
