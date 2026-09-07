"""Programmatic entry points.

Everything the CLI does is available here, so ReviewMindBot can be used as a
library without shelling out or re-implementing the wiring.
"""

from __future__ import annotations

from pathlib import Path

from .cache import NullCache, ResponseCache
from .config import Config, load_config
from .core.diff_parser import DiffParser, FileChange
from .engine.aggregator import Aggregator
from .engine.file_router import FileRouter
from .engine.models import ReviewResult
from .engine.orchestrator import Orchestrator
from .engine.reviewer import Reviewer
from .engine.test_generator import GeneratedTests, TestGenerator
from .errors import DiffSourceError
from .integration.github import GitHubClient, PullRequest, parse_pull_request
from .integration.publisher import PublishOutcome, publish_review
from .llm.base import LLMProvider
from .llm.factory import create_provider
from .usage import Budget


def parse_diff(diff_text: str) -> list[FileChange]:
    return DiffParser().parse(diff_text)


def read_diff_file(path: str | Path) -> str:
    file_path = Path(path)
    try:
        return file_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise DiffSourceError(f"Diff file not found: {file_path}") from None
    except IsADirectoryError:
        raise DiffSourceError(f"Not a file: {file_path}") from None
    except OSError as exc:
        raise DiffSourceError(f"Could not read {file_path}: {exc}") from exc


def load_diff(
    *,
    diff_file: str | Path | None = None,
    pr_url: str | None = None,
    config: Config | None = None,
) -> str:
    """Read a diff from a file or a GitHub PR."""
    if pr_url:
        config = config or load_config()
        client = GitHubClient(config.github_token, config.request_timeout)
        return client.fetch_diff(parse_pull_request(pr_url))
    if diff_file:
        return read_diff_file(diff_file)
    raise DiffSourceError("Provide either a diff file or a PR URL.")


def build_cache(config: Config) -> ResponseCache:
    if not config.cache_enabled:
        return NullCache()
    return ResponseCache(ttl_seconds=config.cache_ttl_seconds)


def build_orchestrator(
    llm: LLMProvider,
    config: Config,
    *,
    cache: ResponseCache | None = None,
) -> Orchestrator:
    budget = Budget(config.budget_usd, llm.model) if config.budget_usd else None
    return Orchestrator(
        reviewer=Reviewer(llm, cache=cache or build_cache(config), budget=budget),
        router=FileRouter(),
        aggregator=Aggregator(),
        max_chunk_size=config.max_chunk_size,
        chunk_overlap=config.chunk_overlap,
        max_concurrency=config.max_concurrency,
    )


def review_diff(
    diff_text: str,
    *,
    config: Config | None = None,
    provider: str | None = None,
    llm: LLMProvider | None = None,
    cache: ResponseCache | None = None,
) -> ReviewResult:
    """Review a unified diff and return structured findings."""
    config = config or load_config()
    llm = llm or create_provider(provider or config.provider, config)
    return build_orchestrator(llm, config, cache=cache).review(parse_diff(diff_text))


def review_pull_request(
    pr_url: str,
    *,
    config: Config | None = None,
    provider: str | None = None,
    llm: LLMProvider | None = None,
    publish: bool = False,
    inline: bool = True,
) -> tuple[ReviewResult, PublishOutcome | None]:
    """Review a GitHub PR and optionally post the findings back to it."""
    config = config or load_config()
    pr = parse_pull_request(pr_url)
    client = GitHubClient(config.github_token, config.request_timeout)

    diff_text = client.fetch_diff(pr)
    files = parse_diff(diff_text)
    llm = llm or create_provider(provider or config.provider, config)
    result = build_orchestrator(llm, config).review(files)

    outcome = None
    if publish:
        outcome = publish_review(client, pr, result, files, inline=inline)

    return result, outcome


def generate_tests(
    diff_text: str,
    *,
    config: Config | None = None,
    provider: str | None = None,
    llm: LLMProvider | None = None,
) -> list[GeneratedTests]:
    """Generate unit tests for code added by a diff."""
    config = config or load_config()
    llm = llm or create_provider(provider or config.provider, config)
    files = FileRouter().select(parse_diff(diff_text))
    return TestGenerator(llm).generate(files)


__all__ = [
    "PullRequest",
    "build_cache",
    "build_orchestrator",
    "generate_tests",
    "load_diff",
    "parse_diff",
    "read_diff_file",
    "review_diff",
    "review_pull_request",
]
