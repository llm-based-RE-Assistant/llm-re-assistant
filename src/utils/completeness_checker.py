class CompletenessChecker:
    def check_4w(self, text):
        issues = []

        keywords = {
            "who": ["user", "system", "admin"],
            "what": ["shall", "must", "should"],
            "when": ["when", "within", "after", "before"],
            "where": ["in", "on", "at"]
        }

        lowered = text.lower()

        for dimension, terms in keywords.items():
            if not any(term in lowered for term in terms):
                issues.append({
                    "type": "missing_condition",
                    "dimension": dimension,
                    "severity": "medium"
                })

        return issues

