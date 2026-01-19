# class ConsistencyChecker:
#     def check(self, text):
#         issues = []
#         lowered = text.lower()

#         contradictions = [
#             ("must login", "no authentication"),
#             ("authentication required", "no authentication required")
#         ]

#         for a, b in contradictions:
#             if a in lowered and b in lowered:
#                 issues.append({
#                     "type": "contradiction",
#                     "details": f"{a} vs {b}",
#                     "severity": "high"
#                 })

#         return issues

# src/utils/consistency_checker.py

class ConsistencyChecker:
    """
    Basic logical consistency checker.
    Detects known contradictions in requirement text.
    """
    def check(self, text: str) -> list:
        issues = []
        lowered = text.lower()

        # List of known contradictory phrase pairs
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


def detect_contradictions(text: str) -> list:
    """
    Wrapper function for ValidationAgent compatibility.
    """
    return ConsistencyChecker().check(text)
