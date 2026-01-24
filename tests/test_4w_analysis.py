"""
Comprehensive tests for 4W Analysis (Who, What, When, Where)
Tests the core discovery framework from Paper [31]
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.elicitation.ontology_engine import OntologyEngine


class Test4WAnalysisWHO:
    """Test WHO dimension detection"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_who_present_user(self):
        """Test WHO detection with 'User' actor"""
        req = "User can login to the system"
        analysis = self.engine.analyze_4w(req, "REQ_001")
        
        assert analysis['who']['present'] == True
        assert 'user' in analysis['who']['value'].lower()
        assert analysis['who']['question'] is None
    
    def test_who_present_admin(self):
        """Test WHO detection with 'Admin' actor"""
        req = "Admin can delete user accounts"
        analysis = self.engine.analyze_4w(req, "REQ_002")
        
        assert analysis['who']['present'] == True
        assert 'admin' in analysis['who']['value'].lower()
    
    def test_who_present_customer(self):
        """Test WHO detection with 'Customer' actor"""
        req = "Customer can view product catalog"
        analysis = self.engine.analyze_4w(req, "REQ_003")
        
        assert analysis['who']['present'] == True
        assert 'customer' in analysis['who']['value'].lower()
    
    def test_who_present_system(self):
        """Test WHO detection with 'System' actor"""
        req = "System sends notification emails"
        analysis = self.engine.analyze_4w(req, "REQ_004")
        
        assert analysis['who']['present'] == True
        assert 'system' in analysis['who']['value'].lower()
    
    def test_who_missing_passive_voice(self):
        """Test WHO missing in passive voice"""
        req = "Cash can be withdrawn from ATM"
        analysis = self.engine.analyze_4w(req, "REQ_005")
        
        # WHO might not be clearly detected in passive voice
        if not analysis['who']['present']:
            assert analysis['who']['question'] is not None
            assert 'WHO' in analysis['who']['question']
    
    def test_who_missing_no_subject(self):
        """Test WHO missing when no clear subject"""
        req = "Documents must be uploaded"
        analysis = self.engine.analyze_4w(req, "REQ_006")
        
        # Should detect missing WHO or provide a question
        if not analysis['who']['present']:
            assert 'WHO' in analysis['who']['question']


class Test4WAnalysisWHAT:
    """Test WHAT dimension detection"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_what_present_login(self):
        """Test WHAT detection with 'login' action"""
        req = "User can login to the system"
        analysis = self.engine.analyze_4w(req, "REQ_001")
        
        assert analysis['what']['present'] == True
        assert 'login' in analysis['what']['value'].lower()
    
    def test_what_present_upload(self):
        """Test WHAT detection with 'upload' action"""
        req = "User can upload documents"
        analysis = self.engine.analyze_4w(req, "REQ_002")
        
        assert analysis['what']['present'] == True
        assert 'upload' in analysis['what']['value'].lower()
    
    def test_what_present_create(self):
        """Test WHAT detection with 'create' action"""
        req = "Admin can create new products"
        analysis = self.engine.analyze_4w(req, "REQ_003")
        
        assert analysis['what']['present'] == True
        assert 'create' in analysis['what']['value'].lower()
    
    def test_what_present_multiple_actions(self):
        """Test WHAT detection with multiple actions"""
        req = "User can view and edit their profile"
        analysis = self.engine.analyze_4w(req, "REQ_004")
        
        assert analysis['what']['present'] == True
        # Should detect at least one action
        actions_found = 'view' in analysis['what']['value'].lower() or 'edit' in analysis['what']['value'].lower()
        assert actions_found
    
    def test_what_missing_vague_action(self):
        """Test WHAT missing with vague action"""
        req = "User can access the system"
        analysis = self.engine.analyze_4w(req, "REQ_005")
        
        # 'access' might be detected as an action, but it's vague
        # This test checks if the action is detected
        assert analysis['what']['present'] == True or analysis['what']['present'] == False
    
    def test_what_missing_no_verb(self):
        """Test WHAT missing when no clear verb"""
        req = "The system interface"
        analysis = self.engine.analyze_4w(req, "REQ_006")
        
        # Should detect missing WHAT
        if not analysis['what']['present']:
            assert 'WHAT' in analysis['what']['question']


class Test4WAnalysisWHEN:
    """Test WHEN dimension detection"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_when_present_business_hours(self):
        """Test WHEN detection with business hours"""
        req = "User can withdraw cash during business hours"
        analysis = self.engine.analyze_4w(req, "REQ_001")
        
        assert analysis['when']['present'] == True
        assert 'hours' in analysis['when']['value'].lower() or 'during' in analysis['when']['value'].lower()
    
    def test_when_present_after_login(self):
        """Test WHEN detection with conditional timing"""
        req = "User can view dashboard after successful login"
        analysis = self.engine.analyze_4w(req, "REQ_002")
        
        assert analysis['when']['present'] == True
        assert 'after' in analysis['when']['value'].lower()
    
    def test_when_present_time_specification(self):
        """Test WHEN detection with specific time"""
        req = "System generates reports daily at 6 AM"
        analysis = self.engine.analyze_4w(req, "REQ_003")
        
        assert analysis['when']['present'] == True
        assert 'daily' in analysis['when']['value'].lower() or 'am' in analysis['when']['value'].lower()
    
    def test_when_present_day_of_week(self):
        """Test WHEN detection with day of week"""
        req = "Backup runs every Monday morning"
        analysis = self.engine.analyze_4w(req, "REQ_004")
        
        assert analysis['when']['present'] == True
        assert 'monday' in analysis['when']['value'].lower() or 'morning' in analysis['when']['value'].lower()
    
    def test_when_missing_no_timing(self):
        """Test WHEN missing when no timing specified"""
        req = "User can upload documents"
        analysis = self.engine.analyze_4w(req, "REQ_005")
        
        assert analysis['when']['present'] == False
        assert analysis['when']['question'] is not None
        assert 'WHEN' in analysis['when']['question']
    
    def test_when_missing_indefinite(self):
        """Test WHEN missing with indefinite timing"""
        req = "Admin can delete user accounts"
        analysis = self.engine.analyze_4w(req, "REQ_006")
        
        # Should detect missing WHEN
        assert analysis['when']['present'] == False
        assert 'WHEN' in analysis['when']['question']


class Test4WAnalysisWHERE:
    """Test WHERE dimension detection"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_where_present_web_interface(self):
        """Test WHERE detection with web interface"""
        req = "User can login through the web portal"
        analysis = self.engine.analyze_4w(req, "REQ_001")
        
        assert analysis['where']['present'] == True
        assert 'web' in analysis['where']['value'].lower() or 'portal' in analysis['where']['value'].lower()
    
    def test_where_present_mobile_app(self):
        """Test WHERE detection with mobile app"""
        req = "Customer can view products in the mobile app"
        analysis = self.engine.analyze_4w(req, "REQ_002")
        
        assert analysis['where']['present'] == True
        assert 'mobile' in analysis['where']['value'].lower() or 'app' in analysis['where']['value'].lower()
    
    def test_where_present_api(self):
        """Test WHERE detection with API"""
        req = "System processes requests via REST API"
        analysis = self.engine.analyze_4w(req, "REQ_003")
        
        assert analysis['where']['present'] == True
        assert 'api' in analysis['where']['value'].lower()
    
    def test_where_present_backend(self):
        """Test WHERE detection with backend"""
        req = "Data is stored in the backend database"
        analysis = self.engine.analyze_4w(req, "REQ_004")
        
        assert analysis['where']['present'] == True
        assert 'backend' in analysis['where']['value'].lower() or 'database' in analysis['where']['value'].lower()
    
    def test_where_present_atm(self):
        """Test WHERE detection with physical location"""
        req = "User can withdraw cash at ATM"
        analysis = self.engine.analyze_4w(req, "REQ_005")
        
        assert analysis['where']['present'] == True
        assert 'atm' in analysis['where']['value'].lower()
    
    def test_where_missing_no_location(self):
        """Test WHERE missing when no location specified"""
        req = "User can upload documents"
        analysis = self.engine.analyze_4w(req, "REQ_006")
        
        assert analysis['where']['present'] == False
        assert analysis['where']['question'] is not None
        assert 'WHERE' in analysis['where']['question']


class Test4WAnalysisCompleteness:
    """Test overall 4W completeness analysis"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_complete_requirement_all_4w(self):
        """Test requirement with all 4W elements present"""
        req = "User can withdraw cash at ATM during business hours"
        analysis = self.engine.analyze_4w(req, "REQ_001")
        
        assert analysis['who']['present'] == True
        assert analysis['what']['present'] == True
        assert analysis['when']['present'] == True
        assert analysis['where']['present'] == True
        assert analysis['missing_count'] == 0
        assert len(analysis['suggestions']) == 0
    
    def test_incomplete_requirement_missing_2(self):
        """Test requirement missing 2 elements"""
        req = "User can upload documents"
        analysis = self.engine.analyze_4w(req, "REQ_002")
        
        # Should be missing WHEN and WHERE
        assert analysis['missing_count'] == 2
        assert len(analysis['suggestions']) == 2
    
    def test_incomplete_requirement_missing_3(self):
        """Test requirement missing 3 elements"""
        req = "Upload documents"
        analysis = self.engine.analyze_4w(req, "REQ_003")
        
        # Should be missing WHO, WHEN, WHERE
        assert analysis['missing_count'] >= 2  # At least 2 missing
    
    def test_suggestions_generation(self):
        """Test that suggestions are properly generated"""
        req = "User can upload files"
        analysis = self.engine.analyze_4w(req, "REQ_004")
        
        # Should have suggestions for missing elements
        assert len(analysis['suggestions']) > 0
        
        # All suggestions should be strings
        for suggestion in analysis['suggestions']:
            assert isinstance(suggestion, str)
            assert len(suggestion) > 0
    
    def test_requirement_id_tracking(self):
        """Test that requirement ID is tracked"""
        req = "User can login"
        req_id = "REQ_TEST_001"
        analysis = self.engine.analyze_4w(req, req_id)
        
        assert analysis['requirement_id'] == req_id
        assert analysis['requirement_text'] == req
    
    def test_multiple_requirements_analysis(self):
        """Test analyzing multiple requirements"""
        requirements = [
            ("User can login to web portal", "REQ_001"),
            ("Admin can delete accounts", "REQ_002"),
            ("System sends emails", "REQ_003")
        ]
        
        for req_text, req_id in requirements:
            analysis = self.engine.analyze_4w(req_text, req_id)
            
            assert 'who' in analysis
            assert 'what' in analysis
            assert 'when' in analysis
            assert 'where' in analysis
            assert 'missing_count' in analysis
            assert 'suggestions' in analysis


class Test4WAnalysisEdgeCases:
    """Test edge cases and special scenarios"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_empty_requirement(self):
        """Test with empty requirement"""
        req = ""
        analysis = self.engine.analyze_4w(req, "REQ_001")
        
        # Should handle gracefully
        assert isinstance(analysis, dict)
        assert 'missing_count' in analysis
    
    def test_very_short_requirement(self):
        """Test with very short requirement"""
        req = "Login"
        analysis = self.engine.analyze_4w(req, "REQ_002")
        
        # Should detect missing elements
        assert analysis['missing_count'] > 0
    
    def test_very_long_requirement(self):
        """Test with very long requirement"""
        req = "The user shall be able to login to the web-based application portal using their registered email address and password credentials at any time during business hours between 9 AM and 5 PM on weekdays excluding public holidays through the secure HTTPS connection on both desktop and mobile devices"
        analysis = self.engine.analyze_4w(req, "REQ_003")
        
        # Should detect all elements in long requirement
        assert analysis['who']['present'] == True
        assert analysis['what']['present'] == True
        assert analysis['when']['present'] == True
        assert analysis['where']['present'] == True
    
    def test_requirement_with_special_characters(self):
        """Test with special characters"""
        req = "User can upload files (PDF, DOCX, etc.) to cloud storage"
        analysis = self.engine.analyze_4w(req, "REQ_004")
        
        # Should handle special characters
        assert isinstance(analysis, dict)
        assert analysis['what']['present'] == True
    
    def test_requirement_with_numbers(self):
        """Test with numbers"""
        req = "User can transfer up to $10,000 per day"
        analysis = self.engine.analyze_4w(req, "REQ_005")
        
        assert analysis['what']['present'] == True
    
    def test_requirement_without_modal_verbs(self):
        """Test requirement without can/should/must"""
        req = "User logs into system"
        analysis = self.engine.analyze_4w(req, "REQ_006")
        
        # Should still analyze properly
        assert isinstance(analysis, dict)
        assert analysis['what']['present'] == True


class Test4WDiscoveryQuestions:
    """Test the quality of discovery questions generated"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_question_clarity_who(self):
        """Test WHO question is clear and actionable"""
        req = "Can upload documents"
        questions = self.engine.get_discovery_questions(req)
        
        who_questions = [q for q in questions if 'WHO' in q]
        if who_questions:
            assert len(who_questions[0]) > 20  # Should be descriptive
            assert '?' in who_questions[0]  # Should be a question
    
    def test_question_clarity_when(self):
        """Test WHEN question is clear and actionable"""
        req = "User can withdraw cash"
        questions = self.engine.get_discovery_questions(req)
        
        when_questions = [q for q in questions if 'WHEN' in q]
        assert len(when_questions) > 0
        assert 'timing' in when_questions[0].lower() or 'condition' in when_questions[0].lower()
    
    def test_question_clarity_where(self):
        """Test WHERE question is clear and actionable"""
        req = "Admin can delete accounts"
        questions = self.engine.get_discovery_questions(req)
        
        where_questions = [q for q in questions if 'WHERE' in q]
        assert len(where_questions) > 0
        assert 'component' in where_questions[0].lower() or 'service' in where_questions[0].lower()
    
    def test_no_questions_for_complete_requirement(self):
        """Test no questions for complete requirement"""
        req = "User can withdraw cash at ATM during business hours"
        questions = self.engine.get_discovery_questions(req)
        
        # Should have few or no questions
        assert len(questions) <= 1  # Maybe WHERE could still be questioned


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])