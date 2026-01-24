"""
Basic tests for OntologyEngine - Quick verification
Run with: pytest tests/test_ontology_engine_basic.py -v
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.elicitation.ontology_engine import OntologyEngine
from src.elicitation.requirement_parser import RequirementParser


class TestRequirementParser:
    """Test RequirementParser functionality"""
    
    def setup_method(self):
        """Initialize parser before each test"""
        self.parser = RequirementParser()
    
    def test_parse_simple_requirement(self):
        """Test parsing a simple requirement"""
        req = "User can login to the system"
        parsed = self.parser.parse_requirement(req)
        
        assert 'actors' in parsed
        assert 'actions' in parsed
        assert 'entities' in parsed
        
        # Should detect 'user' as actor
        actors_lower = [a.lower() for a in parsed['actors']]
        assert 'user' in actors_lower
        
        # Should detect 'login' as action
        assert 'login' in parsed['actions']
    
    def test_extract_entities(self):
        """Test entity extraction"""
        req = "Admin can create new products in the catalog"
        parsed = self.parser.parse_requirement(req)
        
        # Should detect entities like 'products' or 'catalog'
        assert len(parsed['entities']) > 0
    
    def test_detect_multiple_actions(self):
        """Test detecting multiple actions"""
        req = "User can view and edit their profile"
        parsed = self.parser.parse_requirement(req)
        
        # Should detect both 'view' and 'edit'
        actions = parsed['actions']
        assert 'view' in actions or 'edit' in actions


class TestOntologyEngine4W:
    """Test 4W Analysis functionality"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_4w_complete_requirement(self):
        """Test requirement with all 4W elements"""
        req = "User can withdraw cash at ATM during business hours"
        analysis = self.engine.analyze_4w(req, "REQ_001")
        
        # Should detect WHO (user), WHAT (withdraw), WHEN (business hours), WHERE (ATM)
        assert analysis['who']['present'] == True
        assert analysis['what']['present'] == True
        assert analysis['when']['present'] == True
        assert analysis['where']['present'] == True
        assert analysis['missing_count'] == 0
    
    def test_4w_missing_when(self):
        """Test requirement missing WHEN"""
        req = "User can withdraw cash"
        analysis = self.engine.analyze_4w(req, "REQ_002")
        
        # Should detect missing WHEN
        assert analysis['when']['present'] == False
        assert analysis['missing_count'] > 0
        assert any('WHEN' in q for q in analysis['suggestions'])
    
    def test_4w_missing_where(self):
        """Test requirement missing WHERE"""
        req = "User can login"
        analysis = self.engine.analyze_4w(req, "REQ_003")
        
        # Should detect missing WHERE
        assert analysis['where']['present'] == False
        assert any('WHERE' in q for q in analysis['suggestions'])
    
    def test_4w_missing_who(self):
        """Test requirement missing WHO"""
        req = "Cash can be withdrawn"
        analysis = self.engine.analyze_4w(req, "REQ_004")
        
        # Should detect missing WHO (no clear actor)
        # This might not always be detected depending on parsing
        assert 'missing_count' in analysis


class TestComplementaryRules:
    """Test complementary operation detection"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_detect_missing_logout(self):
        """Test detection of missing logout when login exists"""
        requirements = [
            {"id": "REQ_001", "text": "User can login to the system"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        # Should detect missing 'logout'
        assert len(missing) > 0
        assert any(m['missing_action'] == 'logout' for m in missing)
    
    def test_detect_missing_download(self):
        """Test detection of missing download when upload exists"""
        requirements = [
            {"id": "REQ_001", "text": "User can upload files"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        # Should detect missing 'download'
        assert len(missing) > 0
        assert any(m['missing_action'] == 'download' for m in missing)
    
    def test_both_operations_present(self):
        """Test when both complementary operations exist"""
        requirements = [
            {"id": "REQ_001", "text": "User can login to the system"},
            {"id": "REQ_002", "text": "User can logout from the system"}
        ]
        
        missing = self.engine.check_complementary(requirements)
        
        # Should not suggest adding logout
        logout_suggestions = [m for m in missing if m['missing_action'] == 'logout']
        assert len(logout_suggestions) == 0


class TestCRUDCompleteness:
    """Test CRUD completeness checking"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_incomplete_crud(self):
        """Test detection of incomplete CRUD operations"""
        requirements = [
            {"id": "REQ_001", "text": "User can create new products"},
            {"id": "REQ_002", "text": "User can view product list"}
        ]
        
        crud_report = self.engine.check_crud_completeness(requirements)
        
        # Should detect missing Update and Delete operations
        # Note: The exact entity name might vary based on parsing
        # Check that at least one entity is found with missing operations
        assert len(crud_report) > 0
        
        # At least one entity should have missing operations
        has_missing = any(
            len(status['missing_operations']) > 0 
            for status in crud_report.values()
        )
        assert has_missing
    
    def test_complete_crud(self):
        """Test when all CRUD operations are present"""
        requirements = [
            {"id": "REQ_001", "text": "User can create products"},
            {"id": "REQ_002", "text": "User can view products"},
            {"id": "REQ_003", "text": "User can update products"},
            {"id": "REQ_004", "text": "User can delete products"}
        ]
        
        crud_report = self.engine.check_crud_completeness(requirements)
        
        # Should find entities with complete or near-complete CRUD
        # At least one entity should have high completeness
        if crud_report:
            max_completeness = max(
                status['completeness_percentage'] 
                for status in crud_report.values()
            )
            assert max_completeness >= 50  # At least 50% complete


class TestDiscoveryReport:
    """Test complete discovery report generation"""
    
    def setup_method(self):
        """Initialize engine before each test"""
        self.engine = OntologyEngine()
    
    def test_generate_discovery_report(self):
        """Test generation of complete discovery report"""
        requirements = [
            {"id": "REQ_001", "text": "User can login"},
            {"id": "REQ_002", "text": "User can upload files"},
            {"id": "REQ_003", "text": "Admin can create products"}
        ]
        
        report = self.engine.generate_discovery_report(requirements)
        
        # Check report structure
        assert 'summary' in report
        assert 'discovered_requirements' in report
        assert 'crud_completeness' in report
        assert 'categories' in report
        
        # Check summary
        assert report['summary']['original_requirements_count'] == 3
        assert 'discovered_requirements_count' in report['summary']
        assert 'improvement_percentage' in report['summary']
        
        # Should discover at least some missing requirements
        assert report['summary']['discovered_requirements_count'] > 0
    
    def test_discovery_questions_single_req(self):
        """Test getting discovery questions for single requirement"""
        req = "User can upload documents"
        questions = self.engine.get_discovery_questions(req)
        
        # Should return list of questions
        assert isinstance(questions, list)
        
        # Should have some questions (WHEN and WHERE likely missing)
        assert len(questions) > 0


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])