from typing import List
from .models import ReviewFindings


class Reviewer:

    def review_file(self, file_change):

        findings = []

        total_changes = file_change.total_added + file_change.total_removed

        if total_changes > 10:
            findings.append(
                ReviewFindings(
                    severity="medium",
                    category="refactor",
                    message="Large file change detected. Consider splitting into smaller PRs.",
                    file_name=file_change.file_name
                )
            )

        if getattr(file_change, "is_deleted", False):
            findings.append(
                ReviewFindings(
                    severity="high",
                    category="bug",
                    message="File was deleted. Ensure this does not break dependencies.",
                    file_name=file_change.file_name
                )
            )



        return findings
    
    def review_hunk(self, hunk):

        findings = []

        if len(hunk.added_lines) > 5:
            findings.append(
                ReviewFindings(
                    severity="low",
                    category="refactor",
                    message="Large hunk detected. Consider smaller logical changes."
                )
            )
        return findings