# tests/test_consistency_checker.py

import unittest
from src.utils.consistency_checker import detect_contradictions, ConsistencyChecker


class TestConsistencyChecker(unittest.TestCase):
    """Test suite for consistency checking functionality"""
    
    def test_detect_contradiction_login(self):
        """Test detection of login/authentication contradiction"""
        text = "User must login but no authentication required"
        contradictions = detect_contradictions(text)
        
        self.assertGreaterEqual(len(contradictions), 1)
        self.assertEqual(contradictions[0]['type'], 'contradiction')
        self.assertEqual(contradictions[0]['severity'], 'high')
    
    def test_detect_contradiction_authentication(self):
        """Test detection of authentication contradiction"""
        text = "Authentication required but no authentication required"
        contradictions = detect_contradictions(text)
        
        self.assertEqual(len(contradictions), 1)
        self.assertIn('authentication', contradictions[0]['details'].lower())
    
    def test_no_contradiction(self):
        """Test when no contradictions present"""
        text = "The user shall login using email and password"
        contradictions = detect_contradictions(text)
        
        self.assertEqual(len(contradictions), 0)
    
    def test_consistency_checker_class(self):
        """Test ConsistencyChecker class directly"""
        checker = ConsistencyChecker()
        text = "Must login, no authentication"
        
        issues = checker.check(text)
        self.assertGreater(len(issues), 0)


if __name__ == '__main__':
    unittest.main()