# tests/test_ambiguity_detector.py

import unittest
from src.utils.ambiguity_detector import (
    detect_vague_terms,
    detect_weak_phrases,
    has_temporal_constraint,
    has_actor,
    detect_ambiguity,
    calculate_quality_score
)


class TestAmbiguityDetector(unittest.TestCase):
    """Test suite for ambiguity detection functionality"""
    
    def test_detect_vague_terms_found(self):
        """Test detection of vague terms"""
        text = "The system shall be fast and user-friendly"
        vague_terms = detect_vague_terms(text)
        
        self.assertIn("fast", vague_terms)
        self.assertIn("user-friendly", vague_terms)
        self.assertEqual(len(vague_terms), 2)
    
    def test_detect_vague_terms_none(self):
        """Test when no vague terms present"""
        text = "The system shall respond within 2 seconds"
        vague_terms = detect_vague_terms(text)
        
        self.assertEqual(len(vague_terms), 0)
    
    def test_detect_weak_phrases_found(self):
        """Test detection of weak phrases"""
        text = "The system should consider user preferences if possible"
        weak_phrases = detect_weak_phrases(text)
        
        self.assertIn("should consider", weak_phrases)
        self.assertIn("if possible", weak_phrases)
    
    def test_detect_weak_phrases_none(self):
        """Test when no weak phrases present"""
        text = "The user shall login using email and password"
        weak_phrases = detect_weak_phrases(text)
        
        self.assertEqual(len(weak_phrases), 0)
    
    def test_has_temporal_constraint_true(self):
        """Test temporal constraint detection - positive case"""
        text = "The system shall respond within 5 seconds"
        self.assertTrue(has_temporal_constraint(text))
        
        text2 = "Users must logout after 30 minutes"
        self.assertTrue(has_temporal_constraint(text2))
    
def test_has_temporal_constraint_false(self):
    """Test temporal constraint detection - negative case"""
    text = "The system shall encrypt user information"  
    self.assertFalse(has_temporal_constraint(text))
    
    def test_has_actor_true(self):
        """Test actor detection - positive case"""
        text = "The user shall be able to reset password"
        self.assertTrue(has_actor(text))
        
        text2 = "The system shall validate input"
        self.assertTrue(has_actor(text2))
    
    def test_has_actor_false(self):
        """Test actor detection - negative case"""
        text = "Password reset shall be available"
        self.assertFalse(has_actor(text))
    
    def test_detect_ambiguity_comprehensive(self):
        """Test comprehensive ambiguity detection"""
        text = "The application should be fast and user-friendly if possible"
        issues = detect_ambiguity(text)
        
        # Should detect vague terms, weak phrases, and missing actor/condition
        self.assertGreater(len(issues), 0)
        
        issue_types = [issue['type'] for issue in issues]
        self.assertIn('vague_term', issue_types)
        self.assertIn('weak_phrase', issue_types)
    
    def test_detect_ambiguity_good_requirement(self):
        """Test ambiguity detection on well-formed requirement"""
        text = "The user shall login within 30 seconds using email and password"
        issues = detect_ambiguity(text)
        
        # Should have minimal or no issues
        self.assertLessEqual(len(issues), 1)
    
    def test_calculate_quality_score_perfect(self):
        """Test quality score calculation for perfect requirement"""
        text = "The user shall authenticate within 5 seconds using OAuth 2.0"
        score = calculate_quality_score(text)
        
        self.assertGreaterEqual(score, 90.0)
        self.assertLessEqual(score, 100.0)
    
    def test_calculate_quality_score_poor(self):
        """Test quality score calculation for poor requirement"""
        text = "The system should be fast and efficient if possible"
        score = calculate_quality_score(text)
        
        self.assertLess(score, 70.0)


if __name__ == '__main__':
    unittest.main()