# src/utils/smt_solver_integration.py

"""
SMT Solver Integration for Tier 2 Validation
Provides formal verification of logical consistency in requirements.

For Iteration 2: Basic pattern-based contradiction detection.
Future iterations will integrate Z3 solver for full SMT reasoning.
"""


def check_with_smt(text: str, context: dict = None) -> list:
    """
    Tier 2: Formal consistency checking using SMT-style reasoning.
    
    Current implementation uses pattern-based detection.
    Future: Will use Z3 solver for full logical verification.
    
    Args:
        text: Requirement text to analyze
        context: Additional context (artifact metadata)
        
    Returns:
        List of issue dictionaries
    """
    text_lower = text.lower()
    issues = []

    # Define contradiction patterns
    contradiction_patterns = [
        # Authentication contradictions
        {
            "pattern": ("must login", "no authentication"),
            "description": "Requirement mandates login but also states no authentication is required"
        },
        {
            "pattern": ("authentication required", "no authentication required"),
            "description": "Direct contradiction about authentication requirement"
        },
        {
            "pattern": ("login", "no login"),
            "description": "Contradictory statements about login requirement"
        },
        
        # Access control contradictions
        {
            "pattern": ("user can access admin", "unless they are admin"),
            "description": "Illogical access control: users can access admin panel unless they are admin"
        },
        {
            "pattern": ("cannot deactivate accounts", "can block login"),
            "description": "Contradictory account management permissions"
        },
        
        # Data handling contradictions
        {
            "pattern": ("allow data deletion", "retain all user data indefinitely"),
            "description": "Cannot both delete data and retain it indefinitely"
        },
        {
            "pattern": ("encrypt data", "store passwords in plain text"),
            "description": "Security contradiction: encryption required but passwords stored in plain text"
        },
        
        # Payment/transaction contradictions
        {
            "pattern": ("withdraw any amount", "max daily withdrawal"),
            "description": "Contradictory withdrawal limits"
        },
        {
            "pattern": ("payment shall be optional", "required for premium features"),
            "description": "Payment cannot be both optional and required"
        },
        {
            "pattern": ("guest checkout", "require login for all purchases"),
            "description": "Cannot allow guest checkout while requiring login for purchases"
        },
        
        # Timing contradictions
        {
            "pattern": ("sent immediately", "except during business hours"),
            "description": "Contradictory timing constraints"
        },
        {
            "pattern": ("response time shall be <1s", "processing may take up to 5s"),
            "description": "Response time constraint contradicts processing time allowance"
        },
        {
            "pattern": ("<1s", "up to 5s"),
            "description": "Contradictory time constraints"
        },
    ]

    # Check for contradictions
    for pattern_info in contradiction_patterns:
        phrase_a, phrase_b = pattern_info["pattern"]
        
        if phrase_a in text_lower and phrase_b in text_lower:
            issues.append({
                "type": "contradiction",
                "details": pattern_info["description"],
                "severity": "high",
                "detected_by": "SMT_Solver_Tier2",
                "phrases": [phrase_a, phrase_b]
            })

    # Check for numerical contradictions
    issues.extend(_check_numerical_contradictions(text_lower))
    
    return issues


def _check_numerical_contradictions(text: str) -> list:
    """
    Detect numerical constraint contradictions.
    
    Example: "max 500" and "unlimited" in same requirement
    
    Args:
        text: Requirement text (lowercased)
        
    Returns:
        List of contradiction issues
    """
    issues = []
    
    # Check for max + unlimited
    if "max" in text and "unlimited" in text:
        issues.append({
            "type": "contradiction",
            "details": "Requirement specifies both a maximum limit and unlimited access",
            "severity": "high",
            "detected_by": "SMT_Numerical_Check"
        })
    
    # Check for mandatory + optional
    if ("required" in text or "must" in text or "shall" in text) and \
       ("optional" in text or "may" in text):
        issues.append({
            "type": "contradiction",
            "details": "Requirement contains both mandatory and optional language",
            "severity": "high",
            "detected_by": "SMT_Modal_Check"
        })
    
    return issues


def verify_logical_consistency(requirements: list) -> dict:
    """
    Verify logical consistency across multiple requirements.
    Future: Will use Z3 for cross-requirement constraint satisfaction.
    
    Args:
        requirements: List of requirement texts
        
    Returns:
        Dictionary with consistency analysis
    """
    # Placeholder for future cross-requirement analysis
    return {
        "status": "not_implemented",
        "message": "Cross-requirement SMT analysis will be implemented in future iterations"
    }