# tests/test_smt_solver.py

import unittest
from src.utils.smt_solver_integration import check_with_smt, _check_numerical_contradictions


class TestSMTSolver(unittest.TestCase):
    """Test suite for SMT solver integration"""
    
    def test_login_contradiction(self):
        """Test detection of login contradiction"""
        text = "User must login, but no authentication required"
        issues = check_with_smt(text)
        
        self.assertGreater(len(issues), 0)
        self.assertEqual(issues[0]['severity'], 'high')
        self.assertEqual(issues[0]['type'], 'contradiction')
    
    def test_authentication_contradiction(self):
        """Test detection of authentication contradiction"""
        text = "Authentication required but no authentication required"
        issues = check_with_smt(text)
        
        self.assertGreater(len(issues), 0)
        self.assertIn('authentication', issues[0]['details'].lower())
    
    def test_data_contradiction(self):
        """Test detection of data handling contradiction"""
        text = "System shall allow data deletion but retain all user data indefinitely"
        issues = check_with_smt(text)
        
        self.assertGreater(len(issues), 0)
    
    def test_payment_contradiction(self):
        """Test detection of payment contradiction"""
        text = "Payment shall be optional but required for premium features"
        issues = check_with_smt(text)
        
        self.assertGreater(len(issues), 0)
    
    def test_numerical_max_unlimited(self):
        """Test detection of max vs unlimited contradiction"""
        text = "Users can withdraw max $500 but have unlimited access"
        issues = _check_numerical_contradictions(text.lower())
        
        self.assertGreater(len(issues), 0)
    
    def test_modal_contradiction(self):
        """Test detection of required vs optional contradiction"""
        text = "Login is required but may be optional for guests"
        issues = _check_numerical_contradictions(text.lower())
        
        self.assertGreater(len(issues), 0)
    
    def test_no_contradiction(self):
        """Test when no contradictions present"""
        text = "The user shall authenticate using email and password"
        issues = check_with_smt(text)
        
        self.assertEqual(len(issues), 0)
    
    def test_multiple_contradictions(self):
        """Test detection of multiple contradictions in one requirement"""
        text = "Users must login with no authentication and payment is optional but required"
        issues = check_with_smt(text)
        
        # Should detect multiple contradictions
        self.assertGreaterEqual(len(issues), 2)


if __name__ == '__main__':
    unittest.main()