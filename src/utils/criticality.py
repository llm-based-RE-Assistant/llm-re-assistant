# src/utils/criticality.py

CRITICAL_KEYWORDS = [
    "authentication",
    "payment",
    "withdraw",
    "security",
    "personal data",
    "data loss"
]


def is_safety_critical(text: str) -> bool:
    """
    Determines whether a requirement is safety- or security-critical.
    Used to decide escalation to Tier 2 (SMT).
    """
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in CRITICAL_KEYWORDS)

