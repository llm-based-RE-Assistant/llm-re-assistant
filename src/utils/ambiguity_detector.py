import json
from pathlib import Path

class AmbiguityDetector:
    def __init__(self, rules_path="config/validation_rules.json"):
        rules = json.loads(Path(rules_path).read_text())
        self.vague_terms = rules["vague_terms"]
        self.weak_phrases = rules["weak_phrases"]
        self.implicit_assumptions = rules["implicit_assumptions"]

    def detect(self, text):
        issues = []
        lowered = text.lower()

        for term in self.vague_terms:
            if term in lowered:
                issues.append({
                    "type": "vague_term",
                    "term": term,
                    "severity": "medium"
                })

        for phrase in self.weak_phrases:
            if phrase in lowered:
                issues.append({
                    "type": "weak_phrase",
                    "phrase": phrase,
                    "severity": "low"
                })

        for assumption in self.implicit_assumptions:
            if assumption in lowered:
                issues.append({
                    "type": "implicit_assumption",
                    "description": assumption,
                    "severity": "high"
                })

        return issues

