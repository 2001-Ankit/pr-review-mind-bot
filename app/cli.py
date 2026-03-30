import sys
import argparse
import logging
import json
from app.core.diff_parser import DiffParser
from app.engine.reviewer import Reviewer
from app.config import get_config, ConfigError
from app.integration.github import fetch_pr_diff
from app.engine.test_case_generation import TestGenerator


def flatten_hunks(files):

    blocks = []

    for file in files:
        for hunk in file.hunks:
            block = f"""
            FILE: {file.file_name}
            {hunk.header}
            {'\n'.join(hunk.raw_lines)}
            """
            blocks.append(block)

    return blocks


def chunk_blocks(blocks, config=None):
    if config is None:
        config = get_config()

    text = "\n\n".join(blocks)

    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.max_chunk_size,
            chunk_overlap=config.chunk_overlap
        )
        return splitter.split_text(text)
    except ModuleNotFoundError:
        chunk_size = config.max_chunk_size
        chunk_overlap = config.chunk_overlap
        step = max(1, chunk_size - chunk_overlap)
        return [text[i:i + chunk_size] for i in range(0, len(text), step)]

def extract_added_code(files):

    added_blocks = []

    for file in files:
        for hunk in file.hunks:

            if not hunk.added_lines:
                continue

            block = f"""
FILE: {file.file_name}

{'\n'.join(hunk.added_lines)}
"""
            added_blocks.append(block)

    return added_blocks

def main():
    parser = argparse.ArgumentParser(
        description="ReviewMindBot - Intelligent PR code review powered by AI"
    )
    parser.add_argument("diff_file", nargs="?", help="Path to diff file")
    parser.add_argument("--pr", help="GitHub PR URL")
    parser.add_argument(
        "--provider",
        choices=["gemini", "openai","groq"],
        help="LLM provider to use (overrides LLM_PROVIDER env var)"
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format for review results"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    parser.add_argument(
    "--generate-tests",
    action="store_true",
    help="Generate unit test cases for newly added code"
)

    args = parser.parse_args()

    # configuration
    try:
        config = get_config()
    except ConfigError as e:
        print(f"Configuration Error: {e}", file=sys.stderr)
        sys.exit(1)

    # logging setup 
    log_level = logging.DEBUG if args.verbose else getattr(logging, config.log_level)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(config.log_file),
            logging.StreamHandler(sys.stderr)
        ]
    )
    logger = logging.getLogger(__name__)

    try:
        # defining provider 
        provider = args.provider or config.llm_provider
        logger.info(f"Using LLM provider: {provider}")
        config.validate_provider_api_key(provider)

        # import the appropriate LLM provider
        if provider == "gemini":
            from app.llm.gemini import GeminiProvider
            llm = GeminiProvider()
        elif provider == "openai":
            from app.llm.openai import OpenAIProvider
            llm = OpenAIProvider()
        elif provider =="groq":
            from app.llm.groq import GroqProvider
            llm = GroqProvider()
        else:
            raise ConfigError(f"Unknown provider: {provider}")

        # Get diff content
        if args.pr:
            logger.info(f"Fetching PR diff from: {args.pr}")
            github_token = getattr(config, "github_token", None)
            diff_text = fetch_pr_diff(args.pr, github_token=github_token)
        elif args.diff_file:
            logger.info(f"Reading diff file: {args.diff_file}")
            with open(args.diff_file, "r", encoding="utf-8") as f:
                diff_text = f.read()
        else:
            parser.print_help()
            return

        # Parse diff
        logger.debug("Parsing diff...")
        diff_parser = DiffParser()
        files = diff_parser.parse(diff_text)
        logger.info(f"Parsed {len(files)} files from diff")

        # Review chunks
        all_findings = []
        reviewer = Reviewer(llm)
        blocks = flatten_hunks(files)
        logger.debug(f"Created {len(blocks)} blocks from hunks")

        chunks = chunk_blocks(blocks, config)
        logger.info(f"Splitting into {len(chunks)} chunks for review")

        for i, chunk in enumerate(chunks, 1):
            logger.debug(f"Reviewing chunk {i}/{len(chunks)}")
            findings = reviewer.review_chunk(chunk)
            all_findings.extend(findings)

        if not all_findings:
            by_severity = {"high": [], "medium": [], "low": []}
            if args.output == "json":
                print(
                    json.dumps(
                        {
                            "summary": {
                                "total": 0,
                                "high": 0,
                                "medium": 0,
                                "low": 0,
                            },
                            "findings": [],
                        },
                        indent=2,
                    )
                )
                logger.info("Review complete. Found 0 issues.")
                return
            # Display results
            print("\n" + "="*50)
            print("REVIEW RESULTS")
            print("="*50 + "\n")
            print("No issues found!")
        else:
            # Group by severity
            by_severity = {"high": [], "medium": [], "low": []}
            for issue in all_findings:
                severity = issue.severity.lower()
                if severity in by_severity:
                    by_severity[severity].append(issue)

            if args.output == "json":
                print(
                    json.dumps(
                        {
                            "summary": {
                                "total": len(all_findings),
                                "high": len(by_severity["high"]),
                                "medium": len(by_severity["medium"]),
                                "low": len(by_severity["low"]),
                            },
                            "findings": [
                                {
                                    "severity": issue.severity,
                                    "category": issue.category,
                                    "message": issue.message,
                                    "file_name": issue.file_name,
                                }
                                for issue in all_findings
                            ],
                        },
                        indent=2,
                    )
                )
                logger.info(f"Review complete. Found {len(all_findings)} issues.")
                return

            # Display results
            print("\n" + "="*50)
            print("REVIEW RESULTS")
            print("="*50 + "\n")

            # Display high severity
            if by_severity["high"]:
                print("HIGH SEVERITY:")
                for issue in by_severity["high"]:
                    print(f"  • [{issue.category}] {issue.message}")
                print()

            # Display medium severity
            if by_severity["medium"]:
                print("MEDIUM SEVERITY:")
                for issue in by_severity["medium"]:
                    print(f"  • [{issue.category}] {issue.message}")
                print()

            # Display low severity
            if by_severity["low"]:
                print("LOW SEVERITY:")
                for issue in by_severity["low"]:
                    print(f"  • [{issue.category}] {issue.message}")

        print(f"\n Summary: {len(all_findings)} issues found")
        print(f"   High: {len(by_severity['high'])}, Medium: {len(by_severity['medium'])}, Low: {len(by_severity['low'])}")
        logger.info(f"Review complete. Found {len(all_findings)} issues.")
        if args.generate_tests:
            print("===="*50)
            print("Generate test cases")
            print("===="*50)
            test_generator = TestGenerator(llm)
            added_code_block = extract_added_code(files)
            if not added_code_block:
                print("No code blocks were found")
            else:
                for block in added_code_block:
                    logger.debug("Generating test cases")
                    tests = test_generator.generate_tests(block)
                    print(tests)

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        print(f"File not found: {e}", file=sys.stderr)
        sys.exit(1)
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        print(f"Configuration Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

