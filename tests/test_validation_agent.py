# tests/test_validation_agent.py

import unittest
from src.agents.validation_agent import ValidationAgent


class TestValidationAgent(unittest.TestCase):
    """Test suite for ValidationAgent - Integration Tests"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.agent = ValidationAgent()
    
    def test_validate_good_requirement(self):
        """Test validation of a well-formed requirement"""
        artifact = {
            "artifact_id": "TEST_001",
            "text": "The user shall authenticate within 5 seconds using OAuth 2.0"
        }
        
        result = self.agent.validate_requirement(artifact)
        
        self.assertIn('validation', result)
        self.assertGreater(result['validation']['confidence_score'], 0.8)
        # Good requirement should stay in Tier 1 unless safety-critical
    
    def test_validate_vague_requirement(self):
        """Test validation of requirement with vague terms"""
        artifact = {
            "artifact_id": "TEST_002",
            "text": "The system shall be fast and user-friendly"
        }
        
        result = self.agent.validate_requirement(artifact)
        
        self.assertIn('validation', result)
        self.assertGreater(len(result['validation']['issues']), 0)
        
        # Check that vague terms are detected
        issue_types = [issue['type'] for issue in result['validation']['issues']]
        self.assertIn('vague_term', issue_types)
    
    def test_validate_contradictory_requirement(self):
        """Test validation of contradictory requirement"""
        artifact = {
            "artifact_id": "TEST_003",
            "text": "User must login but no authentication required"
        }
        
        result = self.agent.validate_requirement(artifact)
        
        self.assertIn('validation', result)
        # Should escalate to Tier 2 due to high severity
        self.assertEqual(result['validation']['validation_tier'], 'tier2_smt')
        
        # Should have contradiction issue
        issue_types = [issue['type'] for issue in result['validation']['issues']]
        self.assertIn('contradiction', issue_types)
    
    def test_validate_safety_critical(self):
        """Test validation of safety-critical requirement"""
        artifact = {
            "artifact_id": "TEST_004",
            "text": "The system shall encrypt all payment data"
        }
        
        result = self.agent.validate_requirement(artifact)
        
        self.assertIn('validation', result)
        # Should be flagged as safety-critical
        self.assertTrue(result['validation']['is_safety_critical'])
        # Should use Tier 2
        self.assertEqual(result['validation']['validation_tier'], 'tier2_smt')
    
    def test_validate_batch(self):
        """Test batch validation"""
        artifacts = [
            {"artifact_id": "BATCH_001", "text": "User shall login within 30 seconds"},
            {"artifact_id": "BATCH_002", "text": "System shall be fast"},
            {"artifact_id": "BATCH_003", "text": "User must login, no authentication"}
        ]
        
        results = self.agent.validate_batch(artifacts)
        
        self.assertEqual(len(results), 3)
        for result in results:
            self.assertIn('validation', result)
    
    def test_escalation_low_confidence(self):
        """Test escalation to Tier 2 for low confidence"""
        artifact = {
            "artifact_id": "TEST_005",
            "text": "The system should be fast, efficient, and user-friendly if possible"
        }
        
        result = self.agent.validate_requirement(artifact)
        
        # Should have many issues and low confidence
        self.assertLess(result['validation']['confidence_score'], 0.7)
        # Should escalate to Tier 2
        self.assertEqual(result['validation']['validation_tier'], 'tier2_smt')
    
    def test_suggestions_generated(self):
        """Test that suggestions are generated for issues"""
        artifact = {
            "artifact_id": "TEST_006",
            "text": "The system shall be reliable"
        }
        
        result = self.agent.validate_requirement(artifact)
        
        # Should have suggestions (either from LLM or fallback)
        self.assertIn('suggestions', result['validation'])
        # If there are issues, there should be suggestions
        if result['validation']['issues']:
            self.assertGreater(len(result['validation']['suggestions']), 0)
    
    def test_project_report_generation(self):
        """Test project report generation"""
        artifacts = [
            {"artifact_id": "RPT_001", "text": "User shall login within 5 seconds"},
            {"artifact_id": "RPT_002", "text": "System shall be fast"},
            {"artifact_id": "RPT_003", "text": "Must login, no authentication"}
        ]
        
        validated = self.agent.validate_batch(artifacts)
        report = self.agent.generate_project_report(validated)
        
        self.assertIn('total_requirements', report)
        self.assertEqual(report['total_requirements'], 3)
        self.assertIn('average_confidence', report)
        self.assertIn('tier1_validations', report)
        self.assertIn('tier2_validations', report)
        self.assertIn('safety_critical_count', report)


if __name__ == '__main__':
    unittest.main()