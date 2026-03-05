import json
from langchain_text_splitters import RecursiveCharacterTextSplitter
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

        try:
            data = json.loads(response)
        except:
            return []

        findings = []

        for item in data:
            findings.append(
                ReviewFindings(
                    severity=item["severity"],
                    category=item["category"],
                    message=item["message"],
                )
            )

        return findings
    
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

        try:
            data = json.loads(response)
        except:
            return []

        findings = []

        for item in data:
            findings.append(
                ReviewFindings(
                    severity=item["severity"],
                    category=item["category"],
                    message=item["message"],
                )
            )

        return findings