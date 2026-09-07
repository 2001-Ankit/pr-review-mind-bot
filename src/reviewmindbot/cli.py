"""Command-line interface.

This module only parses arguments, wires components, and prints. All behaviour
lives in :mod:`reviewmindbot.api` and the engine.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

from . import __version__, api
from .cache import ResponseCache
from .config import Config, load_config
from .engine.models import ReviewResult, Severity
from .errors import ReviewMindBotError
from .integration.github import GitHubClient, parse_pull_request
from .integration.publisher import publish_review
from .llm.factory import available_providers, create_provider
from .reporting.formatters import FORMATTERS
from .usage import format_usage

logger = logging.getLogger("reviewmindbot")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_FINDINGS = 2

_FAIL_ON_RANK = {
    "none": 0,
    "low": Severity.LOW.rank,
    "medium": Severity.MEDIUM.rank,
    "high": Severity.HIGH.rank,
}


def _force_utf8_output() -> None:
    """Make stdout/stderr able to carry the characters we print.

    Markdown output and PR comment bodies contain emoji and box characters.
    On a Windows console the default encoding is cp1252, which raises
    UnicodeEncodeError on those and takes down an otherwise successful review.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):  # pragma: no cover - exotic stream types
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reviewmindbot",
        description="LLM-powered pull request review.",
        epilog=(
            "Examples:\n"
            "  reviewmindbot changes.diff\n"
            "  git diff main | reviewmindbot -\n"
            "  reviewmindbot --pr https://github.com/owner/repo/pull/12 --comment\n"
            "  reviewmindbot changes.diff --fail-on high --budget-usd 0.50\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "diff_file",
        nargs="?",
        help="Path to a unified diff file, or '-' to read stdin",
    )
    parser.add_argument("--pr", metavar="URL", help="GitHub pull request URL")
    parser.add_argument(
        "--provider",
        choices=available_providers(),
        help="LLM provider (overrides LLM_PROVIDER)",
    )
    parser.add_argument("--model", help="Model name (overrides the provider default)")
    parser.add_argument(
        "--output",
        choices=sorted(FORMATTERS),
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--fail-on",
        choices=sorted(_FAIL_ON_RANK),
        default="none",
        help="Exit with code 2 when a finding of this severity or higher exists",
    )
    parser.add_argument(
        "--generate-tests",
        action="store_true",
        help="Also generate unit tests for newly added code",
    )

    posting = parser.add_argument_group("pull request comments (requires --pr)")
    posting.add_argument(
        "--comment",
        action="store_true",
        help="Post findings to the PR: inline comments plus a summary comment",
    )
    posting.add_argument(
        "--no-inline",
        action="store_true",
        help="With --comment, post only the summary comment",
    )

    cost = parser.add_argument_group("cost control")
    cost.add_argument(
        "--budget-usd",
        type=float,
        metavar="USD",
        help="Stop before exceeding this spend; partial results are still reported",
    )
    cost.add_argument("--no-cache", action="store_true", help="Ignore the response cache")
    cost.add_argument(
        "--clear-cache",
        action="store_true",
        help="Delete every cached response and exit",
    )
    cost.add_argument(
        "--estimate",
        action="store_true",
        help="Report the projected token count and cost, then exit without calling the model",
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    parser.add_argument("--quiet", "-q", action="store_true", help="Errors only")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def configure_logging(config: Config, *, verbose: bool, quiet: bool) -> None:
    """Log to stderr always; add a file handler only if we can write one."""
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.ERROR
    else:
        level = getattr(logging, config.log_level, logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]

    try:
        log_path = Path(config.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    except OSError:
        # A read-only or missing log directory must never stop a review.
        pass

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True,
    )


def apply_overrides(config: Config, args: argparse.Namespace) -> Config:
    """Command-line flags win over environment configuration."""
    changes: dict = {}
    if args.model:
        changes["model"] = args.model
    if args.budget_usd:
        changes["budget_usd"] = args.budget_usd
    if args.no_cache:
        changes["cache_enabled"] = False
    return replace(config, **changes) if changes else config


def _read_diff(args: argparse.Namespace, config: Config) -> str:
    if args.diff_file == "-":
        return sys.stdin.read()
    return api.load_diff(diff_file=args.diff_file, pr_url=args.pr, config=config)


def _should_fail(result: ReviewResult, fail_on: str) -> bool:
    threshold = _FAIL_ON_RANK[fail_on]
    if threshold == 0:
        return False
    return any(finding.severity.rank >= threshold for finding in result.findings)


def _print_estimate(diff_text: str, config: Config, provider_name: str) -> int:
    """Report projected cost without calling the model."""
    from .core.chunking import build_chunks
    from .engine.file_router import FileRouter
    from .engine.prompts import REVIEW_SYSTEM_PROMPT
    from .usage import cost_of, estimate_tokens, price_for

    files = FileRouter().select(api.parse_diff(diff_text))
    chunks = build_chunks(files, config.max_chunk_size, config.chunk_overlap)
    model = config.resolve_model(provider_name)

    input_tokens = sum(
        estimate_tokens(REVIEW_SYSTEM_PROMPT + chunk.text) for chunk in chunks
    )
    output_tokens = 800 * len(chunks)

    print(f"Provider:       {provider_name} ({model})")
    print(f"Files:          {len(files)}")
    print(f"Requests:       {len(chunks)}")
    print(f"Input tokens:   ~{input_tokens:,}")
    print(f"Output tokens:  ~{output_tokens:,} (assumed)")

    if price_for(model) is None:
        print(f"Estimated cost: unknown - no published price for {model}")
    else:
        print(f"Estimated cost: ~${cost_of(model, input_tokens, output_tokens):.4f}")

    print("\nEstimates only. Caching and skipped files reduce the real figure.")
    return EXIT_OK


def _publish(args: argparse.Namespace, config: Config, result, diff_text: str) -> None:
    pr = parse_pull_request(args.pr)
    client = GitHubClient(config.github_token, config.request_timeout)
    outcome = publish_review(
        client,
        pr,
        result,
        api.parse_diff(diff_text),
        inline=not args.no_inline,
    )
    logger.info("Published to %s: %s", pr.slug, outcome.describe())


def run(args: argparse.Namespace) -> int:
    config = apply_overrides(load_config(), args)
    configure_logging(config, verbose=args.verbose, quiet=args.quiet)

    provider_name = args.provider or config.provider

    if args.comment and not args.pr:
        raise ReviewMindBotError("--comment needs --pr to know which PR to post to.")
    if args.comment and not config.github_token:
        raise ReviewMindBotError(
            "--comment needs GITHUB_TOKEN with pull-requests: write permission."
        )

    diff_text = _read_diff(args, config)

    if args.estimate:
        return _print_estimate(diff_text, config, provider_name)

    logger.info(
        "Provider: %s (model: %s)", provider_name, config.resolve_model(provider_name)
    )
    llm = create_provider(provider_name, config)

    if not diff_text.strip():
        logger.warning("Diff is empty; nothing to review.")
        print(FORMATTERS[args.output](ReviewResult()))
        return EXIT_OK

    cache = api.build_cache(config)
    try:
        result = api.review_diff(diff_text, config=config, llm=llm, cache=cache)
    finally:
        cache.close()

    print(FORMATTERS[args.output](result))

    if args.generate_tests:
        _print_generated_tests(diff_text, config, llm)

    if args.comment:
        _publish(args, config, result, diff_text)

    logger.info(
        "Review complete: %d finding(s), %s",
        len(result.findings),
        format_usage(llm.usage),
    )
    return EXIT_FINDINGS if _should_fail(result, args.fail_on) else EXIT_OK


def _print_generated_tests(diff_text: str, config: Config, llm) -> None:
    suites = api.generate_tests(diff_text, config=config, llm=llm)
    print("\n" + "=" * 60)
    print("GENERATED TESTS")
    print("=" * 60)
    if not suites:
        print("\nNo newly added code substantial enough to test.")
        return
    for suite in suites:
        print(f"\n# --- tests for {suite.file_name} ---\n")
        print(suite.code)


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.clear_cache:
        cache = ResponseCache()
        cache.clear()
        cache.close()
        print(f"Cache cleared: {cache.path}")
        return EXIT_OK

    if not args.diff_file and not args.pr:
        parser.print_help()
        return EXIT_OK

    if args.diff_file and args.pr:
        parser.error("Give either a diff file or --pr, not both.")

    try:
        return run(args)
    except ReviewMindBotError as exc:
        # Expected failures: a clean message, no traceback.
        logger.debug("Handled error", exc_info=True)
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:  # genuinely unexpected - show the trace
        logger.exception("Unexpected error: %s", exc)
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
