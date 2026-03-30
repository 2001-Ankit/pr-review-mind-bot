import json
from .models import ReviewFindings


class Reviewer:

    def __init__(self, llm):
        self.llm = llm

    def review_hunk(self, hunk):

        system_prompt = """
            You are a senior software engineer reviewing a pull request.

            You MUST return ONLY valid JSON.
            Do NOT include markdown.
            Do NOT include explanation text.
            Do NOT wrap response in code blocks.

            Return a JSON array in this format:

            [
            {
                "severity": "low | medium | high",
                "category": "bug | refactor | test | security",
                "message": "short actionable feedback"
            }
            ]

            If there are no issues, return an empty array: []
            """

        user_prompt = f"""
                Review this code change:

                {hunk.raw_lines if hasattr(hunk, "raw_lines") else hunk.header}

                Return format:

                [
                {{
                    "severity": "low|medium|high",
                    "category": "bug|refactor|test|security",
                    "message": "string"
                }}
                ]
                """

        response = self.llm.generate(system_prompt, user_prompt)
        return self._parse_findings(response)

    def review_chunk(self, chunk):

        system_prompt = """
            You are a senior software engineer reviewing a pull request.

            Return ONLY valid JSON:

            [
            {
            "severity": "low | medium | high",
            "category": "bug | refactor | test | security",
            "message": "short actionable feedback"
            }
            ]

            If no issues return []
            """

        user_prompt = f"""
            Review this pull request chunk:

            {chunk}
            """

        response = self.llm.generate(system_prompt, user_prompt)
        return self._parse_findings(response)

    def review_file(self, file_change):
        """Review a whole file when routing decides not to split by hunk."""
        raw_lines = []
        for hunk in file_change.hunks:
            raw_lines.extend(hunk.raw_lines)

        block = f"""
        FILE: {file_change.file_name}
        {'\n'.join(raw_lines)}
        """
        return self.review_chunk(block)

    def _parse_findings(self, response):
        """Parse and lightly validate an LLM JSON response."""
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            return []

        if not isinstance(data, list):
            return []

        findings = []
        valid_severities = {"low", "medium", "high"}
        valid_categories = {"bug", "refactor", "test", "security"}

        for item in data:
            if not isinstance(item, dict):
                continue

            severity = str(item.get("severity", "")).lower().strip()
            category = str(item.get("category", "")).lower().strip()
            message = str(item.get("message", "")).strip()

            if severity not in valid_severities:
                continue
            if category not in valid_categories:
                continue
            if not message:
                continue

            findings.append(
                ReviewFindings(
                    severity=severity,
                    category=category,
                    message=message,
                    file_name=item.get("file_name"),
                )
            )

        return findings
