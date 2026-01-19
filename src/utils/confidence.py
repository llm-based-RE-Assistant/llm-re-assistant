# src/utils/confidence.py

def calculate_confidence(issues: list) -> float:
    """
    Calculates a confidence score based on the number and severity of issues.
    
    Args:
        issues (list): List of issue dictionaries
        
    Returns:
        float: Confidence score between 0.0 and 1.0
    """
    if not issues:
        return 1.0
    
    num_issues = len(issues)  # Get the COUNT of issues, not the list
    
    # Base calculation: reduce confidence by 15% per issue
    confidence = 1.0 - (num_issues * 0.15)
    
    # Apply severity weights
    severity_penalty = 0.0
    for issue in issues:
        severity = issue.get("severity", "low")
        if severity == "high":
            severity_penalty += 0.2
        elif severity == "medium":
            severity_penalty += 0.1
        elif severity == "low":
            severity_penalty += 0.05
    
    confidence -= severity_penalty
    
    # Ensure confidence stays between 0.0 and 1.0
    return max(0.0, min(1.0, confidence))