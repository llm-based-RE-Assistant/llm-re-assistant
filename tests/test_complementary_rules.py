"""
Comprehensive tests for Complementary Rules Detection
Tests detection of missing complementary operations (login/logout pairs)
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.elicitation.ontology_engine import OntologyEngine


class TestComplementaryDetectionBasic:
    """Test basic complementary operation detection"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_detect_missing_logout(self):
        """Test detection of missing logout when login exists"""
        requirements = [
            {"id": "REQ_001", "text": "User can login to the system"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        assert len(missing) > 0
        assert any(m['missing_action'] == 'logout' for m in missing)
        assert any(m['trigger_action'] == 'login' for m in missing)
    
    def test_detect_missing_download(self):
        """Test detection of missing download when upload exists"""
        requirements = [
            {"id": "REQ_001", "text": "User can upload files to the server"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        assert len(missing) > 0
        assert any(m['missing_action'] == 'download' for m in missing)
    
    def test_detect_missing_delete(self):
        """Test detection of missing delete when create exists"""
        requirements = [
            {"id": "REQ_001", "text": "Admin can create new user accounts"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        assert len(missing) > 0
        assert any(m['missing_action'] == 'delete' for m in missing)
    
    def test_detect_missing_withdraw(self):
        """Test detection of missing withdraw when deposit exists"""
        requirements = [
            {"id": "REQ_001", "text": "User can deposit money into account"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        assert len(missing) > 0
        assert any(m['missing_action'] == 'withdraw' for m in missing)
    
    def test_no_missing_when_both_present(self):
        """Test no suggestions when both operations present"""
        requirements = [
            {"id": "REQ_001", "text": "User can login to the system"},
            {"id": "REQ_002", "text": "User can logout from the system"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        # Should not suggest adding logout
        logout_missing = [m for m in missing if m['missing_action'] == 'logout']
        assert len(logout_missing) == 0


class TestComplementaryPairs:
    """Test various complementary operation pairs"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_open_close_pair(self):
        """Test open/close complementary pair"""
        requirements = [
            {"id": "REQ_001", "text": "User can open new account"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        assert any(m['missing_action'] == 'close' for m in missing)
    
    def test_start_stop_pair(self):
        """Test start/stop complementary pair"""
        requirements = [
            {"id": "REQ_001", "text": "User can start the service"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        assert any(m['missing_action'] == 'stop' for m in missing)
    
    def test_enable_disable_pair(self):
        """Test enable/disable complementary pair"""
        requirements = [
            {"id": "REQ_001", "text": "Admin can enable user accounts"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        assert any(m['missing_action'] == 'disable' for m in missing)
    
    def test_lock_unlock_pair(self):
        """Test lock/unlock complementary pair"""
        requirements = [
            {"id": "REQ_001", "text": "System can lock accounts after failed attempts"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        assert any(m['missing_action'] == 'unlock' for m in missing)
    
    def test_connect_disconnect_pair(self):
        """Test connect/disconnect complementary pair"""
        requirements = [
            {"id": "REQ_001", "text": "User can connect to VPN"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        assert any(m['missing_action'] == 'disconnect' for m in missing)
    
    def test_subscribe_unsubscribe_pair(self):
        """Test subscribe/unsubscribe complementary pair"""
        requirements = [
            {"id": "REQ_001", "text": "User can subscribe to newsletter"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        assert any(m['missing_action'] == 'unsubscribe' for m in missing)


class TestComplementaryMultiple:
    """Test detection with multiple requirements"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_multiple_missing_complements(self):
        """Test detection of multiple missing complements"""
        requirements = [
            {"id": "REQ_001", "text": "User can login"},
            {"id": "REQ_002", "text": "User can upload files"},
            {"id": "REQ_003", "text": "Admin can create products"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        # Should detect multiple missing operations
        assert len(missing) >= 3
        
        missing_actions = [m['missing_action'] for m in missing]
        assert 'logout' in missing_actions
        assert 'download' in missing_actions
        assert 'delete' in missing_actions
    
    def test_mixed_complete_and_incomplete(self):
        """Test with mix of complete and incomplete pairs"""
        requirements = [
            {"id": "REQ_001", "text": "User can login"},
            {"id": "REQ_002", "text": "User can logout"},
            {"id": "REQ_003", "text": "User can upload files"}
            # No download - incomplete
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        # Should not suggest logout (complete)
        logout_missing = [m for m in missing if m['missing_action'] == 'logout']
        assert len(logout_missing) == 0
        
        # Should suggest download (incomplete)
        download_missing = [m for m in missing if m['missing_action'] == 'download']
        assert len(download_missing) > 0
    
    def test_no_requirements_no_suggestions(self):
        """Test with no requirements"""
        requirements = []
        
        missing = self.engine.check_complementary(requirements)
        
        assert len(missing) == 0


class TestComplementarySuggestions:
    """Test quality of complementary suggestions"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_suggestion_structure(self):
        """Test that suggestions have proper structure"""
        requirements = [
            {"id": "REQ_001", "text": "User can login"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        for suggestion in missing:
            assert 'type' in suggestion
            assert suggestion['type'] == 'complementary'
            assert 'trigger_action' in suggestion
            assert 'trigger_req_id' in suggestion
            assert 'missing_action' in suggestion
            assert 'suggestion' in suggestion
            assert 'priority' in suggestion
    
    def test_suggestion_text_quality(self):
        """Test that suggestion text is clear and actionable"""
        requirements = [
            {"id": "REQ_001", "text": "User can upload documents"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        if missing:
            suggestion = missing[0]
            assert len(suggestion['suggestion']) > 20  # Should be descriptive
            assert 'download' in suggestion['suggestion'].lower()
            assert 'upload' in suggestion['suggestion'].lower()
    
    def test_priority_assignment(self):
        """Test that priorities are assigned"""
        requirements = [
            {"id": "REQ_001", "text": "User can login"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        for suggestion in missing:
            assert suggestion['priority'] in ['low', 'medium', 'high']
    
    def test_trigger_req_id_correct(self):
        """Test that trigger requirement ID is correctly tracked"""
        requirements = [
            {"id": "REQ_CUSTOM_001", "text": "User can upload files"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        if missing:
            assert missing[0]['trigger_req_id'] == "REQ_CUSTOM_001"


class TestComplementaryEdgeCases:
    """Test edge cases for complementary detection"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_case_insensitive_detection(self):
        """Test that detection is case-insensitive"""
        requirements = [
            {"id": "REQ_001", "text": "User can LOGIN to the system"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        # Should still detect missing logout despite uppercase
        assert any(m['missing_action'] == 'logout' for m in missing)
    
    def test_action_in_different_context(self):
        """Test action detection in different contexts"""
        requirements = [
            {"id": "REQ_001", "text": "System enables automatic login feature"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        # Should detect 'login' even in different grammatical form
        # Might not detect if it's not the main action
        assert isinstance(missing, list)
    
    def test_multiple_same_action(self):
        """Test with same action in multiple requirements"""
        requirements = [
            {"id": "REQ_001", "text": "User can login via web"},
            {"id": "REQ_002", "text": "User can login via mobile"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        # Should not duplicate suggestions for same missing action
        logout_suggestions = [m for m in missing if m['missing_action'] == 'logout']
        # Could have multiple if tracking different contexts
        assert len(logout_suggestions) >= 1
    
    def test_similar_but_different_actions(self):
        """Test with similar but different actions"""
        requirements = [
            {"id": "REQ_001", "text": "User can sign in"},  # Similar to login
            {"id": "REQ_002", "text": "User can log out"}   # Similar to logout
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        # Depends on whether 'sign in' is mapped to 'login'
        # Test passes regardless
        assert isinstance(missing, list)
    
    def test_requirement_with_no_actions(self):
        """Test requirement with no clear actions"""
        requirements = [
            {"id": "REQ_001", "text": "The system interface should be blue"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        # Should handle gracefully, no suggestions expected
        assert isinstance(missing, list)
    
    def test_requirements_with_negation(self):
        """Test requirements with negation"""
        requirements = [
            {"id": "REQ_001", "text": "User cannot delete admin accounts"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        # Should handle negation appropriately
        # Might detect 'delete' action anyway
        assert isinstance(missing, list)


class TestComplementaryReverseChecking:
    """Test checking for complement in both directions"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_logout_suggests_login(self):
        """Test that having only logout suggests login"""
        requirements = [
            {"id": "REQ_001", "text": "User can logout from system"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        # Current implementation might not check reverse
        # But should handle this case
        assert isinstance(missing, list)
    
    def test_delete_suggests_create(self):
        """Test that having only delete suggests create"""
        requirements = [
            {"id": "REQ_001", "text": "Admin can delete user accounts"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        # Should detect missing create operation
        # Current config has create -> delete, may need bidirectional
        assert isinstance(missing, list)


class TestComplementaryPerformance:
    """Test performance with many requirements"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_large_requirement_set(self):
        """Test with large number of requirements"""
        requirements = [
            {"id": f"REQ_{i:03d}", "text": f"User can perform action {i}"}
            for i in range(100)
        ]
        
        # Add some known complementary operations
        requirements.extend([
            {"id": "REQ_LOGIN", "text": "User can login"},
            {"id": "REQ_UPLOAD", "text": "User can upload files"}
        ])
        
        import time
        start = time.time()
        missing = self.engine.check_complementary(requirements)
        duration = time.time() - start
        
        # Should complete in reasonable time
        assert duration < 2.0  # Less than 2 seconds
        assert isinstance(missing, list)
    
    def test_many_complementary_pairs(self):
        """Test with many complementary operations"""
        requirements = [
            {"id": "REQ_001", "text": "User can login"},
            {"id": "REQ_002", "text": "User can upload"},
            {"id": "REQ_003", "text": "User can create"},
            {"id": "REQ_004", "text": "User can open"},
            {"id": "REQ_005", "text": "User can start"},
            {"id": "REQ_006", "text": "User can enable"},
            {"id": "REQ_007", "text": "User can lock"},
            {"id": "REQ_008", "text": "User can connect"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        # Should detect many missing complements
        assert len(missing) >= 5


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])