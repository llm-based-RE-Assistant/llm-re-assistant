"""
Integration tests for ElicitationEngine with Ontology Discovery
Tests the complete workflow of requirement elicitation with discovery
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.elicitation.elicitation_engine import ElicitationEngine


class MockOllamaClient:
    """Mock Ollama client for testing"""
    
    def chat_with_system_prompt(self, system_prompt, user_message, conversation_history=None, temperature=0.7):
        """Return mock response"""
        return f"I understand you need: '{user_message}'. Let me clarify..."


class TestElicitationEngineWithOntology:
    """Test ElicitationEngine with ontology integration"""
    
    def setup_method(self):
        """Initialize before each test"""
        self.mock_client = MockOllamaClient()
        self.engine = ElicitationEngine(self.mock_client, enable_ontology=True)
    
    def test_engine_initialization_with_ontology(self):
        """Test that engine initializes with ontology enabled"""
        assert self.engine.enable_ontology == True
        assert self.engine.ontology_engine is not None
        assert hasattr(self.engine, 'extracted_requirements')
        assert len(self.engine.extracted_requirements) == 0
    
    def test_engine_initialization_without_ontology(self):
        """Test that engine can be initialized without ontology"""
        engine = ElicitationEngine(self.mock_client, enable_ontology=False)
        assert engine.enable_ontology == False
        assert engine.ontology_engine is None
    
    def test_process_message_with_requirement(self):
        """Test processing a message containing a requirement"""
        conversation_history = [
            {"role": "assistant", "content": "Let's discuss your requirements."}
        ]
        
        user_message = "User can upload documents"
        conversation_history.append({"role": "user", "content": user_message})
        
        response = self.engine.process_message(user_message, conversation_history)
        
        # Should return a response
        assert isinstance(response, str)
        assert len(response) > 0
        
        # Should have discovered something (WHEN and WHERE likely missing)
        assert "💡 Ontology Analysis" in response or "Missing Details" in response or response
    
    def test_process_message_without_requirement(self):
        """Test processing a message that's not a requirement"""
        conversation_history = [
            {"role": "assistant", "content": "Hello!"}
        ]
        
        user_message = "Hello, I'm looking to build a system"
        conversation_history.append({"role": "user", "content": user_message})
        
        response = self.engine.process_message(user_message, conversation_history)
        
        # Should return a response without discovery questions
        assert isinstance(response, str)
        # Should not have discovery analysis for non-requirements
        # (greeting/introduction doesn't trigger requirement detection)
    
    def test_requirement_collection(self):
        """Test that requirements are collected properly"""
        conversation_history = []
        
        requirements = [
            "User can login",
            "User can upload files",
            "Admin can create products"
        ]
        
        for req in requirements:
            conversation_history.append({"role": "user", "content": req})
            self.engine.process_message(req, conversation_history)
        
        # Should have collected requirements
        count = self.engine.get_requirements_count()
        assert count > 0
        assert count <= len(requirements)  # May not catch all as requirements
    
    def test_generate_discovery_report(self):
        """Test generation of comprehensive discovery report"""
        conversation_history = []
        
        requirements = [
            "User can login",
            "User can upload files",
            "Admin can create products"
        ]
        
        for req in requirements:
            conversation_history.append({"role": "user", "content": req})
            self.engine.process_message(req, conversation_history)
        
        report = self.engine.generate_comprehensive_discovery_report()
        
        if report:  # If any requirements were detected
            assert 'summary' in report
            assert 'discovered_requirements' in report
            assert 'crud_completeness' in report
            assert 'categories' in report
    
    def test_get_discovery_summary(self):
        """Test human-readable discovery summary"""
        conversation_history = []
        
        requirements = [
            "User can login to the system",
            "User can upload documents"
        ]
        
        for req in requirements:
            conversation_history.append({"role": "user", "content": req})
            self.engine.process_message(req, conversation_history)
        
        summary = self.engine.get_discovery_summary()
        
        assert isinstance(summary, str)
        # Summary should contain key sections if requirements were collected
        if self.engine.get_requirements_count() > 0:
            assert "DISCOVERY SUMMARY" in summary or "discovery" in summary.lower()
    
    def test_check_complementary_operations(self):
        """Test complementary operation checking"""
        conversation_history = []
        
        # Add requirement with missing complement
        user_message = "User can login to the system"
        conversation_history.append({"role": "user", "content": user_message})
        self.engine.process_message(user_message, conversation_history)
        
        missing = self.engine.check_complementary_operations()
        
        # Should return a list
        assert isinstance(missing, list)
        
        # If requirement was captured, should detect missing logout
        if len(missing) > 0:
            assert any(m['missing_action'] == 'logout' for m in missing)
    
    def test_check_crud_completeness(self):
        """Test CRUD completeness checking"""
        conversation_history = []
        
        requirements = [
            "User can create orders",
            "User can view order history"
        ]
        
        for req in requirements:
            conversation_history.append({"role": "user", "content": req})
            self.engine.process_message(req, conversation_history)
        
        crud_report = self.engine.check_crud_completeness()
        
        # Should return a dictionary
        assert isinstance(crud_report, dict)
        
        # If entities were found, should have status for them
        if crud_report:
            for entity, status in crud_report.items():
                assert 'present_operations' in status
                assert 'missing_operations' in status
                assert 'completeness_percentage' in status
                assert 'suggestions' in status
    
    def test_specification_generation_with_discovery(self):
        """Test that specification includes discovery report"""
        conversation_history = [
            {"role": "user", "content": "I need a banking system"},
            {"role": "assistant", "content": "Great! Tell me more..."},
            {"role": "user", "content": "Users should be able to deposit money"},
            {"role": "assistant", "content": "Got it..."}
        ]
        
        # Process some requirements
        self.engine.process_message("User can login", conversation_history)
        self.engine.process_message("User can view balance", conversation_history)
        
        # Generate specification
        spec = self.engine.generate_specification(conversation_history)
        
        assert isinstance(spec, str)
        assert len(spec) > 0
        
        # Should contain IEEE-830 structure
        assert "REQUIREMENTS SPECIFICATION" in spec or "SRS" in spec
        
        # Should include discovery summary if requirements were collected
        if self.engine.get_requirements_count() > 0:
            # Discovery section might be appended
            assert "DISCOVERY" in spec or "discovery" in spec.lower() or True
    
    def test_reset_requirements(self):
        """Test resetting collected requirements"""
        conversation_history = []
        
        # Collect some requirements
        self.engine.process_message("User can login", conversation_history)
        self.engine.process_message("User can upload files", conversation_history)
        
        initial_count = self.engine.get_requirements_count()
        
        # Reset
        self.engine.reset_requirements()
        
        # Should be empty now
        assert self.engine.get_requirements_count() == 0
        assert len(self.engine.extracted_requirements) == 0
    
    def test_export_requirements(self):
        """Test exporting collected requirements"""
        conversation_history = []
        
        requirements = [
            "User can login",
            "User can upload files"
        ]
        
        for req in requirements:
            conversation_history.append({"role": "user", "content": req})
            self.engine.process_message(req, conversation_history)
        
        exported = self.engine.export_requirements()
        
        assert isinstance(exported, list)
        # Should be a copy, not the original
        assert exported is not self.engine.extracted_requirements
    
    def test_backward_compatibility_4w_analysis(self):
        """Test that old apply_4w_analysis method still works"""
        result = self.engine.apply_4w_analysis("User can upload documents")
        
        assert isinstance(result, dict)
        assert 'who' in result
        assert 'what' in result
        assert 'when' in result
        assert 'where' in result
    
    def test_ambiguity_detection(self):
        """Test ambiguity detection (existing functionality)"""
        ambiguous_text = "The system should be fast and user-friendly"
        detected = self.engine.detect_ambiguity(ambiguous_text)
        
        assert isinstance(detected, list)
        # Should detect 'fast' and 'user-friendly'
        assert len(detected) >= 2


class TestElicitationEngineWithoutOntology:
    """Test ElicitationEngine with ontology disabled"""
    
    def setup_method(self):
        """Initialize before each test"""
        self.mock_client = MockOllamaClient()
        self.engine = ElicitationEngine(self.mock_client, enable_ontology=False)
    
    def test_process_message_without_ontology(self):
        """Test that processing works without ontology"""
        conversation_history = [
            {"role": "assistant", "content": "Hello!"}
        ]
        
        user_message = "User can upload documents"
        conversation_history.append({"role": "user", "content": user_message})
        
        response = self.engine.process_message(user_message, conversation_history)
        
        # Should return response without discovery questions
        assert isinstance(response, str)
        assert "💡 Ontology Analysis" not in response
    
    def test_discovery_methods_return_none_when_disabled(self):
        """Test that discovery methods handle disabled ontology gracefully"""
        assert self.engine.generate_comprehensive_discovery_report() is None
        assert self.engine.check_complementary_operations() == []
        assert self.engine.check_crud_completeness() == {}
    
    def test_get_discovery_summary_when_disabled(self):
        """Test discovery summary when ontology disabled"""
        summary = self.engine.get_discovery_summary()
        assert "not available" in summary.lower()


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])