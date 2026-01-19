# tests/test_confidence.py

import unittest
from src.utils.confidence import calculate_confidence


class TestConfidenceCalculation(unittest.TestCase):
    """Test suite for confidence score calculation"""
    
    def test_no_issues_perfect_confidence(self):
        """Test confidence with no issues"""
        issues = []
        confidence = calculate_confidence(issues)
        
        self.assertEqual(confidence, 1.0)
    
    def test_low_severity_issues(self):
        """Test confidence with low severity issues"""
        issues = [
            {"type": "weak_phrase", "severity": "low"},
            {"type": "weak_phrase", "severity": "low"}
        ]
        confidence = calculate_confidence(issues)
        
        # Should be reduced but not drastically
        self.assertGreater(confidence, 0.5)
        self.assertLess(confidence, 1.0)
    
    def test_medium_severity_issues(self):
        """Test confidence with medium severity issues"""
        issues = [
            {"type": "vague_term", "severity": "medium"},
            {"type": "missing_actor", "severity": "medium"}
        ]
        confidence = calculate_confidence(issues)
        
        self.assertGreater(confidence, 0.4)
        self.assertLess(confidence, 0.8)
    
    def test_high_severity_issues(self):
        """Test confidence with high severity issues"""
        issues = [
            {"type": "contradiction", "severity": "high"}
        ]
        confidence = calculate_confidence(issues)
        
        # High severity should significantly reduce confidence
        self.assertLess(confidence, 0.7)
    
    def test_mixed_severity_issues(self):
        """Test confidence with mixed severity issues"""
        issues = [
            {"type": "contradiction", "severity": "high"},
            {"type": "vague_term", "severity": "medium"},
            {"type": "weak_phrase", "severity": "low"}
        ]
        confidence = calculate_confidence(issues)
        
        # Multiple issues of varying severity
        self.assertGreater(confidence, 0.0)
        self.assertLess(confidence, 0.6)
    
    def test_confidence_bounds(self):
        """Test that confidence stays within [0, 1] bounds"""
        # Create many issues to test lower bound
        issues = [{"type": "issue", "severity": "high"} for _ in range(20)]
        confidence = calculate_confidence(issues)
        
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)


if __name__ == '__main__':
    unittest.main()