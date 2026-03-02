class Aggregator:

    def aggregate(self, findings_list):
        all_findings = []

        for findings in findings_list:
            all_findings.extend(findings)

        severity_order = {"high": 3, "medium": 2, "low": 1}
        all_findings.sort(
            key=lambda x: severity_order.get(x.severity, 0),
            reverse=True
        )

        return all_findings