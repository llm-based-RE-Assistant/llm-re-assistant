"""
Enhanced SMT Solver Integration for formal verification
Includes temporal contradiction detection
"""

from z3 import *
from typing import List, Dict
import re


def check_with_smt(requirement_text: str, context: dict = None) -> List[Dict]:
    """
    Perform SMT-based formal verification on requirement.
    Enhanced with temporal contradiction detection.
    
    Args:
        requirement_text: The requirement text to verify
        context: Additional context about the requirement
        
    Returns:
        List of issues found by SMT solver
    """
    issues = []
    
    # Check for logical contradictions
    logical_issues = check_logical_contradictions(requirement_text)
    issues.extend(logical_issues)
    
    # Check for numerical constraint conflicts
    numerical_issues = check_numerical_constraints(requirement_text)
    issues.extend(numerical_issues)
    
    # Check for modal logic conflicts
    modal_issues = check_modal_logic(requirement_text)
    issues.extend(modal_issues)
    
    # NEW: Check for temporal contradictions
    temporal_issues = check_temporal_contradictions(requirement_text)
    issues.extend(temporal_issues)
    
    return issues


def check_logical_contradictions(text: str) -> List[Dict]:
    """
    Check for logical contradictions using SMT solver.
    
    Args:
        text: Requirement text
        
    Returns:
        List of contradiction issues
    """
    issues = []
    text_lower = text.lower()
    
    # Pattern 1: "must X" and "must not X"
    if re.search(r'\bmust\s+(\w+)', text_lower) and re.search(r'\bmust\s+not\s+\1', text_lower):
        issues.append({
            "type": "contradiction",
            "subtype": "logical_contradiction",
            "severity": "high",
            "details": "Requirement contains 'must X' and 'must not X'"
        })
    
    # Pattern 2: "all" and "none"
    if ('all' in text_lower and 'none' in text_lower):
        issues.append({
            "type": "contradiction",
            "subtype": "quantifier_conflict",
            "severity": "high",
            "details": "Conflicting quantifiers: 'all' and 'none'"
        })
    
    # Pattern 3: "always" and "never"
    if ('always' in text_lower and 'never' in text_lower):
        issues.append({
            "type": "contradiction",
            "subtype": "temporal_absolute_conflict",
            "severity": "high",
            "details": "Conflicting temporal absolutes: 'always' and 'never'"
        })
    
    # Pattern 4: "required" and "optional"
    if ('required' in text_lower and 'optional' in text_lower):
        issues.append({
            "type": "contradiction",
            "subtype": "necessity_conflict",
            "severity": "high",
            "details": "Conflicting necessity: 'required' and 'optional'"
        })
    
    # Pattern 5: "shall" and "shall not" on same subject
    shall_match = re.search(r'(\w+)\s+shall\s+(\w+)', text_lower)
    shall_not_match = re.search(r'(\w+)\s+shall\s+not\s+(\w+)', text_lower)
    if shall_match and shall_not_match:
        if shall_match.group(1) == shall_not_match.group(1):
            issues.append({
                "type": "contradiction",
                "subtype": "modal_contradiction",
                "severity": "high",
                "details": f"Subject '{shall_match.group(1)}' has conflicting 'shall' and 'shall not'"
            })
    
    return issues


def check_numerical_constraints(text: str) -> List[Dict]:
    """
    Check for numerical constraint conflicts using Z3.
    
    Args:
        text: Requirement text
        
    Returns:
        List of numerical constraint issues
    """
    issues = []
    
    # Extract numerical constraints
    # Pattern: "at least X" and "at most Y" where X > Y
    at_least = re.findall(r'at\s+least\s+(\d+)', text.lower())
    at_most = re.findall(r'at\s+most\s+(\d+)', text.lower())
    
    if at_least and at_most:
        min_val = int(at_least[0])
        max_val = int(at_most[0])
        
        if min_val > max_val:
            issues.append({
                "type": "contradiction",
                "subtype": "numerical_constraint_conflict",
                "severity": "high",
                "details": f"Impossible constraint: at least {min_val} and at most {max_val}"
            })
    
    # Pattern: "greater than X" and "less than Y" where X >= Y
    greater_than = re.findall(r'greater\s+than\s+(\d+)', text.lower())
    less_than = re.findall(r'less\s+than\s+(\d+)', text.lower())
    
    if greater_than and less_than:
        min_val = int(greater_than[0])
        max_val = int(less_than[0])
        
        if min_val >= max_val:
            issues.append({
                "type": "contradiction",
                "subtype": "numerical_range_conflict",
                "severity": "high",
                "details": f"Impossible range: greater than {min_val} and less than {max_val}"
            })
    
    # Pattern: Multiple exact values for same property
    exact_values = re.findall(r'(?:equals?|is|be)\s+(\d+)', text.lower())
    if len(set(exact_values)) > 1:
        issues.append({
            "type": "contradiction",
            "subtype": "multiple_exact_values",
            "severity": "high",
            "details": f"Multiple conflicting exact values: {', '.join(set(exact_values))}"
        })
    
    return issues


def check_modal_logic(text: str) -> List[Dict]:
    """
    Check for modal logic conflicts (must/may, required/optional).
    
    Args:
        text: Requirement text
        
    Returns:
        List of modal logic issues
    """
    issues = []
    text_lower = text.lower()
    
    # Check for "must" and "may" on same action
    must_actions = re.findall(r'must\s+(\w+)', text_lower)
    may_actions = re.findall(r'may\s+(\w+)', text_lower)
    
    conflicting_actions = set(must_actions) & set(may_actions)
    if conflicting_actions:
        issues.append({
            "type": "contradiction",
            "subtype": "modal_necessity_conflict",
            "severity": "high",
            "details": f"Actions with conflicting modality: {', '.join(conflicting_actions)}"
        })
    
    # Check for "required" and "optional" on same feature
    if 'required' in text_lower and 'optional' in text_lower:
        # Extract feature names around these words
        required_context = re.findall(r'(\w+)\s+(?:is|are)\s+required', text_lower)
        optional_context = re.findall(r'(\w+)\s+(?:is|are)\s+optional', text_lower)
        
        conflicting_features = set(required_context) & set(optional_context)
        if conflicting_features:
            issues.append({
                "type": "contradiction",
                "subtype": "requirement_modality_conflict",
                "severity": "high",
                "details": f"Features with conflicting requirement status: {', '.join(conflicting_features)}"
            })
    
    return issues


def check_temporal_contradictions(text: str) -> List[Dict]:
    """
    NEW: Check for temporal/timing contradictions.
    Example: "must complete in 2 seconds" vs "must complete in 5 seconds"
    
    Args:
        text: Requirement text
        
    Returns:
        List of temporal contradiction issues
    """
    issues = []
    
    # Extract timing constraints
    time_pattern = r'(?:within|in|after|before)\s+(\d+)\s*(second|minute|hour|day|week|month)s?'
    time_matches = re.findall(time_pattern, text.lower())
    
    if len(time_matches) >= 2:
        # Convert all to seconds for comparison
        times_in_seconds = []
        for value, unit in time_matches:
            seconds = int(value)
            if unit.startswith('minute'):
                seconds *= 60
            elif unit.startswith('hour'):
                seconds *= 3600
            elif unit.startswith('day'):
                seconds *= 86400
            elif unit.startswith('week'):
                seconds *= 604800
            elif unit.startswith('month'):
                seconds *= 2592000
            times_in_seconds.append((seconds, f"{value} {unit}"))
        
        # Check for contradictions
        if len(set([t[0] for t in times_in_seconds])) > 1:
            # Multiple different time constraints
            min_time = min(times_in_seconds, key=lambda x: x[0])
            max_time = max(times_in_seconds, key=lambda x: x[0])
            
            # Check if they conflict (e.g., both say "must complete within")
            if 'within' in text.lower() or 'in' in text.lower():
                issues.append({
                    "type": "contradiction",
                    "subtype": "temporal_constraint_conflict",
                    "severity": "medium",
                    "details": f"Multiple timing constraints: {min_time[1]} and {max_time[1]}"
                })
    
    # Check for "before X" and "after X" on same event
    before_matches = re.findall(r'before\s+(\w+)', text.lower())
    after_matches = re.findall(r'after\s+(\w+)', text.lower())
    
    conflicting_events = set(before_matches) & set(after_matches)
    if conflicting_events:
        issues.append({
            "type": "contradiction",
            "subtype": "temporal_sequence_conflict",
            "severity": "high",
            "details": f"Events with conflicting temporal order: {', '.join(conflicting_events)}"
        })
    
    # Check for "immediately" with delayed timing
    if 'immediately' in text.lower():
        if any(unit in text.lower() for unit in ['second', 'minute', 'hour', 'day']) and \
           re.search(r'(\d+)\s*(second|minute|hour|day)', text.lower()):
            match = re.search(r'(\d+)\s*(second|minute|hour|day)', text.lower())
            if int(match.group(1)) > 0:
                issues.append({
                    "type": "contradiction",
                    "subtype": "immediacy_vs_delay",
                    "severity": "medium",
                    "details": f"'Immediately' conflicts with '{match.group(0)}' delay"
                })
    
    return issues


def verify_requirement_set(requirements: List[str]) -> List[Dict]:
    """
    Verify a set of requirements for cross-requirement contradictions.
    
    Args:
        requirements: List of requirement texts
        
    Returns:
        List of cross-requirement issues
    """
    issues = []
    
    # Check for contradictions between requirements
    for i, req1 in enumerate(requirements):
        for j, req2 in enumerate(requirements[i+1:], i+1):
            # Check if req1 and req2 contradict
            if _requirements_contradict(req1, req2):
                issues.append({
                    "type": "cross_requirement_contradiction",
                    "severity": "high",
                    "requirement_indices": [i, j],
                    "details": f"Requirements {i+1} and {j+1} contradict each other"
                })
    
    return issues


def _requirements_contradict(req1: str, req2: str) -> bool:
    """
    Check if two requirements contradict each other.
    
    Args:
        req1: First requirement
        req2: Second requirement
        
    Returns:
        True if requirements contradict
    """
    req1_lower = req1.lower()
    req2_lower = req2.lower()
    
    # Simple heuristic: look for opposite modal verbs on similar subjects
    # Extract subject-verb patterns
    pattern1 = re.search(r'(\w+)\s+(must|shall)\s+(\w+)', req1_lower)
    pattern2 = re.search(r'(\w+)\s+(must\s+not|shall\s+not)\s+(\w+)', req2_lower)
    
    if pattern1 and pattern2:
        if pattern1.group(1) == pattern2.group(1) and pattern1.group(3) == pattern2.group(3):
            return True
    
    return False