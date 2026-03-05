import sys
import argparse
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.core.diff_parser import DiffParser
from app.engine.reviewer import Reviewer
from app.llm.gemini import GeminiProvider
from app.integration.github import fetch_pr_diff


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


def chunk_blocks(blocks):

    text = "\n\n".join(blocks)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50
    )

    return splitter.split_text(text)

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("diff_file", nargs="?", help="Path to diff file")
    parser.add_argument("--pr", help="GitHub PR URL")

    args = parser.parse_args()

    if args.pr:
        diff_text = fetch_pr_diff(args.pr)
        print(diff_text)

    elif args.diff_file:
        with open(args.diff_file, "r", encoding="utf-8") as f:
            diff_text = f.read()

    else:
        print("Provide a diff file or --pr URL")
        return

    diff_parser = DiffParser()
    files = diff_parser.parse(diff_text)
    all_findings = []


    llm = GeminiProvider()
    reviewer = Reviewer(llm)
    
    blocks = flatten_hunks(files)

    chunks = chunk_blocks(blocks)

    for chunk in chunks:
        findings = reviewer.review_chunk(chunk)
        all_findings.extend(findings)
        print("\n=== Review Results ===\n")
    for issue in all_findings:
        print(
            f"[{issue.severity.upper()}] "
            f"{issue.category} - "
            f"{issue.message}"
        )


if __name__ == "__main__":
    main()

