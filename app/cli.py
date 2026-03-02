import sys
from app.core.diff_parser import DiffParser
from app.engine.reviewer import Reviewer


def main():

    if len(sys.argv) < 2:
        print("Usage: python -m app.cli <diff_file>")
        return

    diff_path = sys.argv[1]

    with open(diff_path, "r", encoding="utf-8") as f:
        diff_text = f.read()


    parser = DiffParser()
    files = parser.parse(diff_text)

    reviewer = Reviewer()
    
    all_findings = []

    for file in files:

        # File-level review
        findings = reviewer.review_file(file)
        all_findings.extend(findings)

        # Hunk-level review
        for hunk in file.hunks:
            hunk_findings = reviewer.review_hunk(hunk)
            all_findings.extend(hunk_findings)

    print("\n=== Review Results ===\n")

    if not all_findings:
        print("No issues detected.")
    else:
        for finding in all_findings:
            print(f"[{finding.severity.upper()}] "
                  f"{finding.category} - "
                  f"{finding.message}")

if __name__ == "__main__":
    main()