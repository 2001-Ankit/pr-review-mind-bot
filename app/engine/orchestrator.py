class Orchestrator:

    def __init__(self, router, reviewer, aggregator):
        self.router = router
        self.reviewer = reviewer
        self.aggregator = aggregator

    def review(self, files):

        all_findings = []

        for file in files:

            if self.router.should_split(file):

                for hunk in file.hunks:
                    findings = self.reviewer.review_hunk(hunk)
                    all_findings.append(findings)

            else:
                findings = self.reviewer.review_file(file)
                all_findings.append(findings)

        return self.aggregator.aggregate(all_findings)