# # src/utils/ambiguity_detector.py

# VAGUE_TERMS = [
#     "fast", "user-friendly", "reliable",
#     "efficient", "secure", "high-quality"
# ]

# WEAK_PHRASES = [
#     "if possible", "as appropriate",
#     "if necessary", "should consider"
# ]


# def detect_ambiguity(text: str) -> list:
#     """
#     Tier 1 heuristic ambiguity detection.
#     """
#     text_lower = text.lower()
#     issues = []

#     for term in VAGUE_TERMS:
#         if term in text_lower:
#             issues.append({
#                 "type": "vague_term",
#                 "term": term,
#                 "severity": "medium"
#             })

#     for phrase in WEAK_PHRASES:
#         if phrase in text_lower:
#             issues.append({
#                 "type": "weak_phrase",
#                 "phrase": phrase,
#                 "severity": "low"
#             })

#     # Simple completeness check (Who / What / When)
#     if "user" not in text_lower and "system" not in text_lower:
#         issues.append({
#             "type": "missing_actor",
#             "description": "Actor not specified",
#             "severity": "medium"
#         })

#     if "when" not in text_lower and "within" not in text_lower:
#         issues.append({
#             "type": "missing_condition",
#             "description": "Temporal constraint missing",
#             "severity": "medium"
#         })

#     return issues
# src/utils/ambiguity_detector.py

VAGUE_TERMS = [
    "fast", "slow", "quick", "user-friendly", "reliable",
    "efficient", "secure", "high-quality", "robust", "scalable",
    "flexible", "simple", "easy", "intuitive", "responsive",
    "adequate", "sufficient", "appropriate", "reasonable", "timely",
    "properly", "correctly", "accurately", "effectively", "efficiently"
]

WEAK_PHRASES = [
    "if possible", "as appropriate", "if necessary", "should consider",
    "may be", "could be", "might be", "as needed", "when required",
    "as much as possible", "to the extent possible", "where feasible",
    "if feasible", "as deemed appropriate", "subject to approval"
]

TEMPORAL_KEYWORDS = [
    "when", "within", "before", "after", "until", "during",
    "at", "by", "in", "seconds", "minutes", "hours", "days"
]

ACTOR_KEYWORDS = [
    "user", "system", "admin", "administrator", "customer",
    "operator", "developer", "manager", "stakeholder", "client"
]


def detect_vague_terms(text: str) -> list:
    """
    Detects vague/ambiguous terms in requirements text.
    Returns a list of vague terms found.
    
    Args:
        text (str): The requirement text to analyze
        
    Returns:
        list: List of vague terms found in the text
    """
    text_lower = text.lower()
    found_terms = []
    
    for term in VAGUE_TERMS:
        if term in text_lower:
            found_terms.append(term)
    
    return found_terms


def detect_weak_phrases(text: str) -> list:
    """
    Detects weak/optional phrases that reduce requirement clarity.
    
    Args:
        text (str): The requirement text to analyze
        
    Returns:
        list: List of weak phrases found in the text
    """
    text_lower = text.lower()
    found_phrases = []
    
    for phrase in WEAK_PHRASES:
        if phrase in text_lower:
            found_phrases.append(phrase)
    
    return found_phrases


def has_temporal_constraint(text: str) -> bool:
    """
    Checks if the requirement has a temporal constraint.
    
    Args:
        text (str): The requirement text to analyze
        
    Returns:
        bool: True if temporal constraint is present, False otherwise
    """
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in TEMPORAL_KEYWORDS)


def has_actor(text: str) -> bool:
    """
    Checks if the requirement specifies an actor.
    
    Args:
        text (str): The requirement text to analyze
        
    Returns:
        bool: True if actor is specified, False otherwise
    """
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in ACTOR_KEYWORDS)


def detect_ambiguity(text: str) -> list:
    """
    Comprehensive Tier 1 heuristic ambiguity detection.
    Detects vague terms, weak phrases, missing actors, and missing temporal constraints.
    
    Args:
        text (str): The requirement text to analyze
        
    Returns:
        list: List of issue dictionaries containing type, details, and severity
    """
    text_lower = text.lower()
    issues = []

    # Check for vague terms
    for term in VAGUE_TERMS:
        if term in text_lower:
            issues.append({
                "type": "vague_term",
                "term": term,
                "severity": "medium"
            })

    # Check for weak phrases
    for phrase in WEAK_PHRASES:
        if phrase in text_lower:
            issues.append({
                "type": "weak_phrase",
                "phrase": phrase,
                "severity": "low"
            })

    # Check for missing actor (Who)
    if not has_actor(text):
        issues.append({
            "type": "missing_actor",
            "description": "Actor not specified (e.g., user, system, admin)",
            "severity": "medium"
        })

    # Check for missing temporal constraint (When)
    if not has_temporal_constraint(text):
        issues.append({
            "type": "missing_condition",
            "description": "Temporal constraint missing (e.g., within X seconds, when Y occurs)",
            "severity": "medium"
        })

    return issues


def analyze_requirement_quality(text: str) -> dict:
    """
    Comprehensive analysis of requirement quality.
    
    Args:
        text (str): The requirement text to analyze
        
    Returns:
        dict: Analysis results including all detected issues and quality metrics
    """
    return {
        "vague_terms": detect_vague_terms(text),
        "weak_phrases": detect_weak_phrases(text),
        "has_actor": has_actor(text),
        "has_temporal_constraint": has_temporal_constraint(text),
        "all_issues": detect_ambiguity(text),
        "quality_score": calculate_quality_score(text)
    }


def calculate_quality_score(text: str) -> float:
    """
    Calculates a quality score for the requirement (0-100).
    Higher score means better quality.
    
    Args:
        text (str): The requirement text to analyze
        
    Returns:
        float: Quality score between 0 and 100
    """
    issues = detect_ambiguity(text)
    
    # Start with perfect score
    score = 100.0
    
    # Deduct points for each issue type
    for issue in issues:
        if issue["severity"] == "high":
            score -= 15
        elif issue["severity"] == "medium":
            score -= 10
        elif issue["severity"] == "low":
            score -= 5
    
    # Ensure score doesn't go below 0
    return max(0.0, score)