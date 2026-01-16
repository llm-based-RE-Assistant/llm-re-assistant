class ConsistencyChecker:
    def check(self, text):
        issues = []
        lowered = text.lower()

        contradictions = [
            ("must login", "no authentication"),
            ("authentication required", "no authentication required")
        ]

        for a, b in contradictions:
            if a in lowered and b in lowered:
                issues.append({
                    "type": "contradiction",
                    "details": f"{a} vs {b}",
                    "severity": "high"
                })

        return issues

