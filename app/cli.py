import sys
from app.core.diff_parser import DiffParser
from app.engine.reviewer import Reviewer
from app.llm.gemini import GeminiProvider


def main():

    if len(sys.argv) < 2:
        print("Usage: python -m app.cli <diff_file>")
        return

    diff_path = sys.argv[1]

    with open(diff_path, "r", encoding="utf-8") as f:
        diff_text = f.read()

    parser = DiffParser()
    files = parser.parse(diff_text)

    llm = GeminiProvider()
    reviewer = Reviewer(llm)

    all_findings = []

    for file in files:
        for hunk in file.hunks:
            findings = reviewer.review_hunk(hunk)
            all_findings.extend(findings)

    print("\n=== Review Results ===\n")

    if not all_findings:
        print("No issues detected.")
    else:
        for finding in all_findings:
            print(
                f"[{finding.severity.upper()}] "
                f"{finding.category} - "
                f"{finding.message}"
            )


if __name__ == "__main__":
    main()