from datetime import datetime

from src.utils.ambiguity_detector import detect_vague_terms, detect_weak_phrases
from src.utils.consistency_checker import detect_contradictions
from src.utils.confidence import calculate_confidence
from src.utils.criticality import is_safety_critical
from src.utils.smt_solver_integration import check_with_smt
from src.agents.suggestion_agent import SuggestionAgent


class ValidationAgent:
    """
    Hybrid validation agent:
    - Tier 1: LLM-based quality checks (fast, heuristic)
    - Tier 2: SMT-based logical consistency checks (formal, for critical requirements)
    - LLM-generated actionable suggestions
    
    Routing Logic:
    - Safety-critical requirements → Always Tier 2
    - Low confidence (<0.7) → Escalate to Tier 2
    - High severity issues → Escalate to Tier 2
    - Otherwise → Tier 1 only
    """

    def __init__(self):
        self.suggestion_agent = SuggestionAgent()

    def validate_requirement(self, artifact: dict) -> dict:
        """
        Validate a single requirement artifact.
        
        Args:
            artifact: Dict with 'artifact_id' and 'text' keys
            
        Returns:
            Artifact dict with added 'validation' key
        """
        text = artifact["text"]
        issues = []

        # -------- Tier 1: Quality / Vagueness Checks --------
        # Detect vague terms
        vague_terms = detect_vague_terms(text)
        for term in vague_terms:
            issues.append({
                "type": "vague_term",
                "term": term,
                "severity": "medium"
            })

        # Detect weak phrases
        weak_phrases = detect_weak_phrases(text)
        for phrase in weak_phrases:
            issues.append({
                "type": "weak_phrase",
                "phrase": phrase,
                "severity": "low"
            })

        # Basic consistency check (Tier 1)
        contradictions = detect_contradictions(text)
        for contradiction in contradictions:
            issues.append(contradiction)

        # -------- Confidence Scoring --------
        confidence_score = calculate_confidence(issues)

        # -------- Determine if Tier 2 is needed --------
        needs_tier2 = self._should_escalate_to_tier2(
            text=text,
            confidence_score=confidence_score,
            issues=issues
        )

        validation_tier = "tier1_llm"
        
        # -------- Tier 2: SMT Solver (if needed) --------
        if needs_tier2:
            validation_tier = "tier2_smt"
            smt_issues = check_with_smt(text, context=artifact)
            
            # Merge SMT issues (avoid duplicates)
            for smt_issue in smt_issues:
                if not any(
                    issue.get('details') == smt_issue.get('details')
                    for issue in issues
                ):
                    issues.append(smt_issue)
            
            # Recalculate confidence after SMT check
            confidence_score = calculate_confidence(issues)

        # -------- LLM Suggestions --------
        suggestions = self.suggestion_agent.generate_suggestions(
            requirement_text=text,
            issues=issues
        )

        # -------- Final Validation Result --------
        validation_result = {
            "validated_by": "ValidationAgent",
            "validated_at": datetime.utcnow().isoformat(),
            "confidence_score": round(confidence_score, 2),
            "issues": issues,
            "suggestions": suggestions,
            "validation_tier": validation_tier,
            "is_safety_critical": is_safety_critical(text)
        }

        artifact["validation"] = validation_result
        return artifact

    def _should_escalate_to_tier2(
        self,
        text: str,
        confidence_score: float,
        issues: list
    ) -> bool:
        """
        Determine if requirement should be escalated to Tier 2 (SMT).
        
        Escalation criteria:
        1. Safety-critical requirement
        2. Confidence score < 0.7
        3. Contains high-severity issues
        
        Args:
            text: Requirement text
            confidence_score: Calculated confidence (0-1)
            issues: List of detected issues
            
        Returns:
            True if should use Tier 2, False otherwise
        """
        # Criterion 1: Safety-critical
        if is_safety_critical(text):
            return True
        
        # Criterion 2: Low confidence
        if confidence_score < 0.7:
            return True
        
        # Criterion 3: High severity issues
        if any(issue.get("severity") == "high" for issue in issues):
            return True
        
        return False

    def validate_batch(self, artifacts: list) -> list:
        """
        Validate multiple requirements in batch.
        
        Args:
            artifacts: List of artifact dicts
            
        Returns:
            List of validated artifacts
        """
        return [self.validate_requirement(artifact) for artifact in artifacts]

    def generate_project_report(self, validated_artifacts: list) -> dict:
        """
        Generate project-level validation report.
        
        Args:
            validated_artifacts: List of artifacts with validation results
            
        Returns:
            Report dictionary with summary statistics
        """
        total_confidence = 0.0
        total_requirements = len(validated_artifacts)
        
        issue_counter = {}
        critical_issues = []
        tier1_count = 0
        tier2_count = 0
        safety_critical_count = 0

        for artifact in validated_artifacts:
            validation = artifact["validation"]
            total_confidence += validation["confidence_score"]
            
            # Count tiers
            if validation["validation_tier"] == "tier2_smt":
                tier2_count += 1
            else:
                tier1_count += 1
            
            # Count safety-critical
            if validation.get("is_safety_critical"):
                safety_critical_count += 1

            # Count issues by type
            for issue in validation["issues"]:
                issue_type = issue["type"]
                issue_counter[issue_type] = issue_counter.get(issue_type, 0) + 1

                # Track critical issues
                if issue.get("severity") == "high":
                    critical_issues.append({
                        "artifact_id": artifact["artifact_id"],
                        "issue": issue
                    })

        return {
            "total_requirements": total_requirements,
            "average_confidence": round(total_confidence / total_requirements, 2) if total_requirements > 0 else 0,
            "tier1_validations": tier1_count,
            "tier2_validations": tier2_count,
            "safety_critical_count": safety_critical_count,
            "total_issues_by_type": issue_counter,
            "critical_issues_count": len(critical_issues),
            "critical_issues": critical_issues
        }