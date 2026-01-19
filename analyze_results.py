#!/usr/bin/env python3
"""
Analyze validation results
"""

from src.agents.validation_agent import ValidationAgent

# Sample requirements to test
test_cases = [
    {
        "id": "GOOD",
        "text": "The user shall authenticate within 5 seconds using OAuth 2.0",
        "expected": "high confidence, tier1"
    },
    {
        "id": "VAGUE",
        "text": "The system shall be fast and user-friendly",
        "expected": "low confidence, many issues"
    },
    {
        "id": "CONTRADICTION",
        "text": "User must login but no authentication required",
        "expected": "tier2, high severity issues"
    },
    {
        "id": "SAFETY_CRITICAL",
        "text": "The system shall encrypt all payment data",
        "expected": "tier2, safety-critical"
    }
]

print("="*70)
print("VALIDATION ANALYSIS")
print("="*70)

agent = ValidationAgent()

for tc in test_cases:
    print(f"\n[{tc['id']}] {tc['text']}")
    print(f"Expected: {tc['expected']}")
    print("-" * 70)
    
    artifact = {"artifact_id": tc['id'], "text": tc['text']}
    result = agent.validate_requirement(artifact)
    
    validation = result['validation']
    
    print(f"Confidence: {validation['confidence_score']}")
    print(f"Tier: {validation['validation_tier']}")
    print(f"Safety Critical: {validation.get('is_safety_critical', False)}")
    print(f"Issues ({len(validation['issues'])}):")
    for issue in validation['issues']:
        print(f"  - {issue['type']}: {issue.get('term', issue.get('details', 'N/A'))} [{issue['severity']}]")
    
    print(f"Suggestions ({len(validation['suggestions'])}):")
    for i, suggestion in enumerate(validation['suggestions'][:3], 1):
        print(f"  {i}. {suggestion}")

print("\n" + "="*70)