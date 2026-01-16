import json
from datetime import datetime

from src.utils.ambiguity_detector import AmbiguityDetector
from src.utils.completeness_checker import CompletenessChecker
from src.utils.consistency_checker import ConsistencyChecker
from src.utils.confidence import calculate_confidence
from src.utils.smt_solver_integration import SMTSolver

class ValidationAgent:
    def __init__(self):
        self.ambiguity = AmbiguityDetector()
        self.completeness = CompletenessChecker()
        self.consistency = ConsistencyChecker()
        self.smt = SMTSolver()

        self.critical_terms = json.loads(
            open("config/criticality_keywords.json").read()
        )["safety_critical"]

    def is_safety_critical(self, text):
        lowered = text.lower()
        return any(term in lowered for term in self.critical_terms)

    def validate_requirement(self, requirement, context=None):
        issues = []

        issues += self.ambiguity.detect(requirement)
        issues += self.completeness.check_4w(requirement)
        issues += self.consistency.check(requirement)

        confidence = calculate_confidence(len(issues))
        validation_tier = "tier1_llm"

        if self.is_safety_critical(requirement) or confidence < 0.7:
            smt_result = self.smt.check_constraints(context or {})
            validation_tier = "tier2_smt"

            if smt_result["status"] == "UNSAT":
                issues.append({
                    "type": "logical_conflict",
                    "severity": "high",
                    "details": smt_result["message"]
                })
                confidence = 0.0

        return {
            "validated_by": "Validation_Agent",
            "validated_at": datetime.utcnow().isoformat(),
            "confidence_score": confidence,
            "issues": issues,
            "validation_tier": validation_tier
        }

