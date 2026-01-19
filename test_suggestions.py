#!/usr/bin/env python3
"""Test suggestion generation"""

from src.agents.suggestion_agent import SuggestionAgent

agent = SuggestionAgent()

# Test with issues that should generate suggestions
issues = [
    {"type": "vague_term", "term": "fast", "severity": "medium"},
    {"type": "weak_phrase", "phrase": "if possible", "severity": "low"}
]

print("Testing suggestion generation...")
print(f"Issues: {issues}")

suggestions = agent.generate_suggestions(
    requirement_text="System should be fast if possible",
    issues=issues
)

print(f"\nSuggestions generated: {len(suggestions)}")
for i, s in enumerate(suggestions, 1):
    print(f"{i}. {s}")

# Test 2: With contradiction
print("\n" + "="*70)
print("Test 2: Contradiction")
issues2 = [
    {"type": "contradiction", "details": "must login vs no authentication", "severity": "high"}
]

suggestions2 = agent.generate_suggestions(
    requirement_text="User must login but no authentication required",
    issues=issues2
)

print(f"\nSuggestions generated: {len(suggestions2)}")
for i, s in enumerate(suggestions2, 1):
    print(f"{i}. {s}")