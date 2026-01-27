"""
Enhanced Validation Agent - Main orchestrator for requirements validation
Implements two-tier hybrid validation with completeness checking
"""

from typing import List, Dict
from datetime import datetime
from src.agents.suggestion_agent import SuggestionAgent
from src.utils.ambiguity_detector import detect_vague_terms, detect_weak_phrases
from src.utils.consistency_checker import detect_contradictions
from src.utils.confidence import calculate_confidence
from src.utils.criticality import is_safety_critical
from src.utils.smt_solver_integration import check_with_smt


class ValidationAgent:
    """
    Main validation agent that orchestrates the validation process.
    Implements two-tier architecture: Tier 1 (LLM) + Tier 2 (SMT).
    """
    
    def __init__(self):
        """Initialize validation agent with suggestion agent"""
        self.suggestion_agent = SuggestionAgent()
    
    def validate_requirement(self, artifact: dict) -> dict:
        """
        Validate a single requirement artifact.
        
        Args:
            artifact: Requirement artifact with 'text' field
            
        Returns:
            Enhanced artifact with validation results
        """
        text = artifact["text"]
        issues = []
        
        # Tier 1: LLM-based quality checks
        
        # Check for vague terms
        vague_terms = detect_vague_terms(text)
        for term in vague_terms:
            issues.append({
                "type": "vague_term",
                "term": term,
                "severity": "medium"
            })
        
        # Check for weak phrases
        weak_phrases = detect_weak_phrases(text)
        for phrase in weak_phrases:
            issues.append({
                "type": "weak_phrase",
                "phrase": phrase,
                "severity": "medium"
            })
        
        # Check completeness (4W framework)
        completeness_issues = self.check_completeness(text)
        issues.extend(completeness_issues)
        
        # Check for basic contradictions
        contradictions = detect_contradictions(text)
        for contradiction in contradictions:
            issues.append(contradiction)
        
        # Calculate initial confidence score
        confidence_score = calculate_confidence(issues)
        
        # Determine if Tier 2 verification is needed
        validation_tier = "tier1_llm"
        needs_tier2 = self._should_escalate_to_tier2(
            text=text,
            confidence_score=confidence_score,
            issues=issues
        )
        
        # Tier 2: SMT solver verification (if needed)
        if needs_tier2:
            validation_tier = "tier2_smt"
            smt_issues = check_with_smt(text, context=artifact)
            
            # Add SMT issues if not already detected
            for smt_issue in smt_issues:
                if not any(
                    issue.get('details') == smt_issue.get('details')
                    for issue in issues
                ):
                    issues.append(smt_issue)
            
            # Recalculate confidence with SMT results
            confidence_score = calculate_confidence(issues)
        
        # Generate suggestions using LLM
        suggestions = self.suggestion_agent.generate_suggestions(
            requirement_text=text,
            issues=issues
        )
        
        # Build validation result
        validation_result = {
            "validated_by": "ValidationAgent",
            "validated_at": datetime.utcnow().isoformat(),
            "confidence_score": round(confidence_score, 2),
            "issues": issues,
            "suggestions": suggestions,
            "validation_tier": validation_tier,
            "is_safety_critical": is_safety_critical(text)
        }
        
        # Add validation to artifact
        artifact["validation"] = validation_result
        
        return artifact
    
    def check_completeness(self, requirement: str) -> List[Dict]:
        """
        Check if requirement is complete using 4W framework.
        Returns list of missing elements as issues.
        
        Args:
            requirement: Requirement text to check
            
        Returns:
            List of completeness issues
        """
        issues = []
        req_lower = requirement.lower()
        
        # WHO check - identify actors
        actor_keywords = ['user', 'system', 'admin', 'administrator', 'customer', 
                         'stakeholder', 'operator', 'manager', 'application']
        if not any(word in req_lower for word in actor_keywords):
            issues.append({
                "type": "missing_who",
                "description": "Requirement does not specify WHO is involved",
                "severity": "medium",
                "suggestion": "Add actor: user, system, admin, etc."
            })
        
        # WHAT check - action/capability
        action_keywords = ['shall', 'must', 'should', 'will', 'can', 'need']
        if not any(word in req_lower for word in action_keywords):
            issues.append({
                "type": "missing_what",
                "description": "Requirement does not clearly specify WHAT action/capability",
                "severity": "high",
                "suggestion": "Use 'shall', 'must', or 'should' to specify action"
            })
        
        # WHEN check (if time-related context exists)
        time_context = ['notify', 'send', 'update', 'synchronize', 'refresh', 
                       'schedule', 'trigger', 'alert', 'process']
        if any(word in req_lower for word in time_context):
            time_keywords = ['when', 'after', 'before', 'within', 'second', 
                           'minute', 'hour', 'day', 'immediately', 'daily', 'weekly']
            if not any(word in req_lower for word in time_keywords):
                issues.append({
                    "type": "missing_when",
                    "description": "Requirement involves timing but doesn't specify WHEN",
                    "severity": "medium",
                    "suggestion": "Add timing constraint: within X seconds, after Y event, etc."
                })
        
        # WHERE check (if location-related context exists)
        location_context = ['display', 'show', 'present', 'appear', 'render', 
                          'view', 'visible', 'accessible']
        if any(word in req_lower for word in location_context):
            location_keywords = ['screen', 'page', 'interface', 'dashboard', 
                               'panel', 'window', 'dialog', 'menu', 'form']
            if not any(word in req_lower for word in location_keywords):
                issues.append({
                    "type": "missing_where",
                    "description": "Requirement involves display/access but doesn't specify WHERE",
                    "severity": "low",
                    "suggestion": "Add location: on screen, in dashboard, via interface, etc."
                })
        
        return issues
    
    def _should_escalate_to_tier2(
        self,
        text: str,
        confidence_score: float,
        issues: list
    ) -> bool:
        """
        Determine if requirement should be escalated to Tier 2 (SMT).
        
        Args:
            text: Requirement text
            confidence_score: Calculated confidence score
            issues: List of detected issues
            
        Returns:
            True if should escalate to Tier 2
        """
        # Escalate if safety-critical
        if is_safety_critical(text):
            return True
        
        # Escalate if low confidence
        if confidence_score < 0.7:
            return True
        
        # Escalate if high-severity issues exist
        if any(issue.get("severity") == "high" for issue in issues):
            return True
        
        return False
    
    def validate_batch(self, artifacts: list) -> list:
        """
        Validate multiple requirements in batch.
        
        Args:
            artifacts: List of requirement artifacts
            
        Returns:
            List of validated artifacts
        """
        return [self.validate_requirement(artifact) for artifact in artifacts]
    
    def generate_project_report(self, validated_artifacts: list) -> dict:
        """
        Generate summary report for all validated requirements.
        
        Args:
            validated_artifacts: List of validated requirement artifacts
            
        Returns:
            Dictionary with aggregate validation metrics
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
            
            # Count validation tiers
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
    
    def add_traceability_metadata(self, validated_requirements: List[Dict], session_id: str = None) -> List[Dict]:
        """
        Add traceability information to requirements.
        Links requirements to conversation messages, stakeholders, etc.
        
        Args:
            validated_requirements: List of validated requirement artifacts
            session_id: Optional session identifier for tracking
            
        Returns:
            Requirements with added traceability metadata
        """
        for req in validated_requirements:
            req['traceability'] = {
                'source_message_id': req.get('message_index'),
                'extracted_at': datetime.utcnow().isoformat(),
                'stakeholder': 'user',
                'iteration': 1,
                'parent_requirement': None,
                'related_requirements': [],
                'session_id': session_id,
                'extraction_method': req.get('source', 'unknown')
            }
        return validated_requirements