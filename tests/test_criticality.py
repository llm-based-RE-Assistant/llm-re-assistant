# tests/test_criticality.py

import unittest
from src.utils.criticality import is_safety_critical


class TestCriticalityDetection(unittest.TestCase):
    """Test suite for safety-critical requirement detection"""
    
    def test_authentication_critical(self):
        """Test that authentication requirements are flagged as critical"""
        text = "The user must provide authentication credentials"
        self.assertTrue(is_safety_critical(text))
    
    def test_payment_critical(self):
        """Test that payment requirements are flagged as critical"""
        text = "The system shall process payment transactions"
        self.assertTrue(is_safety_critical(text))
    
    def test_withdraw_critical(self):
        """Test that withdrawal requirements are flagged as critical"""
        text = "Users can withdraw up to $500 daily"
        self.assertTrue(is_safety_critical(text))
    
    def test_data_loss_critical(self):
        """Test that data loss requirements are flagged as critical"""
        text = "The system must prevent data loss during shutdown"
        self.assertTrue(is_safety_critical(text))
    
    def test_security_critical(self):
        """Test that security requirements are flagged as critical"""
        text = "All personal data must be encrypted"
        self.assertTrue(is_safety_critical(text))
    
    def test_non_critical_requirement(self):
        """Test that non-critical requirements are not flagged"""
        text = "The user interface shall display a welcome message"
        self.assertFalse(is_safety_critical(text))
    
    def test_multiple_critical_keywords(self):
        """Test requirement with multiple critical keywords"""
        text = "Payment authentication must be secure to prevent data loss"
        self.assertTrue(is_safety_critical(text))


if __name__ == '__main__':
    unittest.main()