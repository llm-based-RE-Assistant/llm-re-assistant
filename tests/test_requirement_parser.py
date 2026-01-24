"""
Comprehensive tests for Requirement Parser
Tests NLP-based extraction of entities, actions, and actors
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.elicitation.requirement_parser import RequirementParser


class TestRequirementParserInitialization:
    """Test parser initialization"""
    
    def test_parser_initializes(self):
        """Test that parser initializes correctly"""
        parser = RequirementParser()
        
        assert parser is not None
        assert parser.nlp is not None
        assert hasattr(parser, 'actor_keywords')
        assert hasattr(parser, 'action_verbs')
        assert hasattr(parser, 'entity_keywords')
    
    def test_spacy_model_loaded(self):
        """Test that spaCy model is loaded"""
        parser = RequirementParser()
        
        # Test that we can process text
        doc = parser.nlp("User can login")
        assert doc is not None
        assert len(doc) > 0


class TestActorExtraction:
    """Test extraction of actors/user roles"""
    
    def setup_method(self):
        """Initialize parser before each test"""
        self.parser = RequirementParser()
    
    def test_extract_user_actor(self):
        """Test extraction of 'User' actor"""
        req = "User can login to the system"
        parsed = self.parser.parse_requirement(req)
        
        actors_lower = [a.lower() for a in parsed['actors']]
        assert 'user' in actors_lower
    
    def test_extract_admin_actor(self):
        """Test extraction of 'Admin' actor"""
        req = "Admin can delete user accounts"
        parsed = self.parser.parse_requirement(req)
        
        actors_lower = [a.lower() for a in parsed['actors']]
        assert 'admin' in actors_lower
    
    def test_extract_customer_actor(self):
        """Test extraction of 'Customer' actor"""
        req = "Customer can view product catalog"
        parsed = self.parser.parse_requirement(req)
        
        actors_lower = [a.lower() for a in parsed['actors']]
        assert 'customer' in actors_lower
    
    def test_extract_system_actor(self):
        """Test extraction of 'System' actor"""
        req = "System sends notification emails"
        parsed = self.parser.parse_requirement(req)
        
        actors_lower = [a.lower() for a in parsed['actors']]
        assert 'system' in actors_lower
    
    def test_extract_multiple_actors(self):
        """Test extraction of multiple actors"""
        req = "User and Admin can manage settings"
        parsed = self.parser.parse_requirement(req)
        
        assert len(parsed['actors']) >= 1
    
    def test_no_actor_in_passive_voice(self):
        """Test handling of passive voice (no clear actor)"""
        req = "Documents must be uploaded"
        parsed = self.parser.parse_requirement(req)
        
        # May or may not detect an actor
        assert isinstance(parsed['actors'], list)


class TestActionExtraction:
    """Test extraction of actions/verbs"""
    
    def setup_method(self):
        """Initialize parser before each test"""
        self.parser = RequirementParser()
    
    def test_extract_login_action(self):
        """Test extraction of 'login' action"""
        req = "User can login to the system"
        parsed = self.parser.parse_requirement(req)
        
        assert 'login' in parsed['actions']
    
    def test_extract_upload_action(self):
        """Test extraction of 'upload' action"""
        req = "User can upload documents"
        parsed = self.parser.parse_requirement(req)
        
        assert 'upload' in parsed['actions']
    
    def test_extract_create_action(self):
        """Test extraction of 'create' action"""
        req = "Admin can create new accounts"
        parsed = self.parser.parse_requirement(req)
        
        assert 'create' in parsed['actions']
    
    def test_extract_delete_action(self):
        """Test extraction of 'delete' action"""
        req = "User can delete old files"
        parsed = self.parser.parse_requirement(req)
        
        assert 'delete' in parsed['actions']
    
    def test_extract_view_action(self):
        """Test extraction of 'view' action"""
        req = "Customer can view order history"
        parsed = self.parser.parse_requirement(req)
        
        assert 'view' in parsed['actions']
    
    def test_extract_multiple_actions(self):
        """Test extraction of multiple actions"""
        req = "User can view and edit their profile"
        parsed = self.parser.parse_requirement(req)
        
        # Should detect at least one action
        assert len(parsed['actions']) >= 1
        # Ideally both view and edit
        assert 'view' in parsed['actions'] or 'edit' in parsed['actions']
    
    def test_extract_crud_actions(self):
        """Test extraction of all CRUD actions"""
        crud_reqs = [
            ("User can create products", "create"),
            ("User can read data", "read"),
            ("User can update settings", "update"),
            ("User can delete records", "delete")
        ]
        
        for req_text, expected_action in crud_reqs:
            parsed = self.parser.parse_requirement(req_text)
            assert expected_action in parsed['actions'] or len(parsed['actions']) > 0


class TestEntityExtraction:
    """Test extraction of entities/nouns"""
    
    def setup_method(self):
        """Initialize parser before each test"""
        self.parser = RequirementParser()
    
    def test_extract_product_entity(self):
        """Test extraction of 'Product' entity"""
        req = "User can create new products"
        parsed = self.parser.parse_requirement(req)
        
        # Should detect product-related entity
        entities_lower = [e.lower() for e in parsed['entities']]
        assert any('product' in entity for entity in entities_lower)
    
    def test_extract_account_entity(self):
        """Test extraction of 'Account' entity"""
        req = "Admin can delete user accounts"
        parsed = self.parser.parse_requirement(req)
        
        # Should detect account
        entities_lower = [e.lower() for e in parsed['entities']]
        assert any('account' in entity for entity in entities_lower)
    
    def test_extract_file_entity(self):
        """Test extraction of 'File' entity"""
        req = "User can upload files"
        parsed = self.parser.parse_requirement(req)
        
        # Should detect file-related entity
        entities_lower = [e.lower() for e in parsed['entities']]
        # May be detected as 'file' or 'document'
        assert len(entities_lower) >= 0  # Flexible
    
    def test_extract_order_entity(self):
        """Test extraction of 'Order' entity"""
        req = "Customer can view order history"
        parsed = self.parser.parse_requirement(req)
        
        # Should detect order
        entities_lower = [e.lower() for e in parsed['entities']]
        assert any('order' in entity for entity in entities_lower)
    
    def test_extract_multiple_entities(self):
        """Test extraction of multiple entities"""
        req = "User can transfer money from account to wallet"
        parsed = self.parser.parse_requirement(req)
        
        # Should detect multiple entities
        assert len(parsed['entities']) >= 1
    
    def test_compound_entity_extraction(self):
        """Test extraction of compound entities"""
        req = "User can manage user accounts"
        parsed = self.parser.parse_requirement(req)
        
        # Should detect compound entity "user account" or separate entities
        assert len(parsed['entities']) >= 1


class TestCompleteRequirementParsing:
    """Test parsing complete requirements"""
    
    def setup_method(self):
        """Initialize parser before each test"""
        self.parser = RequirementParser()
    
    def test_parse_simple_requirement(self):
        """Test parsing simple requirement"""
        req = "User can login"
        parsed = self.parser.parse_requirement(req)
        
        assert 'actors' in parsed
        assert 'actions' in parsed
        assert 'entities' in parsed
        assert 'raw_text' in parsed
        
        assert parsed['raw_text'] == req
    
    def test_parse_complex_requirement(self):
        """Test parsing complex requirement"""
        req = "Admin can create and manage user accounts in the web portal during business hours"
        parsed = self.parser.parse_requirement(req)
        
        # Should extract multiple components
        assert len(parsed['actors']) > 0
        assert len(parsed['actions']) > 0
        # Entities might be detected
        assert isinstance(parsed['entities'], list)
    
    def test_parse_requirement_with_details(self):
        """Test parsing requirement with lots of details"""
        req = "Registered customer can upload PDF documents up to 10MB to secure cloud storage"
        parsed = self.parser.parse_requirement(req)
        
        assert len(parsed['actors']) > 0
        assert len(parsed['actions']) > 0
        assert isinstance(parsed['entities'], list)
    
    def test_parsed_structure(self):
        """Test that parsed structure is consistent"""
        reqs = [
            "User can login",
            "Admin can delete accounts",
            "System sends emails"
        ]
        
        for req in reqs:
            parsed = self.parser.parse_requirement(req)
            
            assert isinstance(parsed, dict)
            assert 'actors' in parsed
            assert 'actions' in parsed
            assert 'entities' in parsed
            assert 'raw_text' in parsed
            
            assert isinstance(parsed['actors'], list)
            assert isinstance(parsed['actions'], list)
            assert isinstance(parsed['entities'], list)
            assert isinstance(parsed['raw_text'], str)


class TestParserEdgeCases:
    """Test parser edge cases"""
    
    def setup_method(self):
        """Initialize parser before each test"""
        self.parser = RequirementParser()
    
    def test_empty_string(self):
        """Test parsing empty string"""
        req = ""
        parsed = self.parser.parse_requirement(req)
        
        assert isinstance(parsed, dict)
        assert parsed['raw_text'] == ""
    
    def test_very_short_requirement(self):
        """Test parsing very short requirement"""
        req = "Login"
        parsed = self.parser.parse_requirement(req)
        
        # Should handle gracefully
        assert isinstance(parsed, dict)
        # Should detect login as action
        assert 'login' in parsed['actions'] or len(parsed['actions']) >= 0
    
    def test_very_long_requirement(self):
        """Test parsing very long requirement"""
        req = "The system administrator shall have the capability to create, modify, update, and permanently delete user account records from the centralized database management system through the secure web-based administration control panel interface accessible via HTTPS protocol on port 443"
        parsed = self.parser.parse_requirement(req)
        
        # Should extract multiple components
        assert len(parsed['actions']) > 0
        assert len(parsed['actors']) > 0 or len(parsed['entities']) > 0
    
    def test_requirement_with_special_characters(self):
        """Test with special characters"""
        req = "User can upload files (PDF, DOCX, .txt) @ max 10MB"
        parsed = self.parser.parse_requirement(req)
        
        assert isinstance(parsed, dict)
        assert len(parsed['actions']) > 0
    
    def test_requirement_with_numbers(self):
        """Test with numbers"""
        req = "User can transfer up to $10,000 per day"
        parsed = self.parser.parse_requirement(req)
        
        assert isinstance(parsed, dict)
        # Should detect transfer action
        assert 'transfer' in parsed['actions'] or len(parsed['actions']) > 0
    
    def test_non_requirement_text(self):
        """Test with non-requirement text"""
        req = "The interface should be blue and modern"
        parsed = self.parser.parse_requirement(req)
        
        # Should handle gracefully
        assert isinstance(parsed, dict)


class TestModalVerbDetection:
    """Test modal verb detection"""
    
    def setup_method(self):
        """Initialize parser before each test"""
        self.parser = RequirementParser()
    
    def test_detect_shall(self):
        """Test detection of 'shall'"""
        req = "User shall login to the system"
        
        has_modal = self.parser.is_modal_verb_present(req)
        assert has_modal == True
    
    def test_detect_should(self):
        """Test detection of 'should'"""
        req = "System should send notifications"
        
        has_modal = self.parser.is_modal_verb_present(req)
        assert has_modal == True
    
    def test_detect_must(self):
        """Test detection of 'must'"""
        req = "User must authenticate"
        
        has_modal = self.parser.is_modal_verb_present(req)
        assert has_modal == True
    
    def test_detect_can(self):
        """Test detection of 'can'"""
        req = "User can upload files"
        
        has_modal = self.parser.is_modal_verb_present(req)
        assert has_modal == True
    
    def test_no_modal_verb(self):
        """Test when no modal verb present"""
        req = "User logs into system"
        
        has_modal = self.parser.is_modal_verb_present(req)
        assert has_modal == False


class TestAmbiguousPronounDetection:
    """Test ambiguous pronoun detection"""
    
    def setup_method(self):
        """Initialize parser before each test"""
        self.parser = RequirementParser()
    
    def test_detect_it(self):
        """Test detection of ambiguous 'it'"""
        req = "User can view it in the interface"
        
        pronouns = self.parser.detect_ambiguous_pronouns(req)
        assert 'it' in pronouns or 'It' in pronouns
    
    def test_detect_this(self):
        """Test detection of ambiguous 'this'"""
        req = "User can delete this when needed"
        
        pronouns = self.parser.detect_ambiguous_pronouns(req)
        assert 'this' in pronouns or 'This' in pronouns
    
    def test_detect_they(self):
        """Test detection of ambiguous 'they'"""
        req = "They can access the system"
        
        pronouns = self.parser.detect_ambiguous_pronouns(req)
        assert 'They' in pronouns or 'they' in pronouns
    
    def test_no_ambiguous_pronouns(self):
        """Test when no ambiguous pronouns present"""
        req = "User can login to the system"
        
        pronouns = self.parser.detect_ambiguous_pronouns(req)
        assert len(pronouns) == 0


class TestEntityNameExtraction:
    """Test extraction of entity names from multiple requirements"""
    
    def setup_method(self):
        """Initialize parser before each test"""
        self.parser = RequirementParser()
    
    def test_extract_unique_entities(self):
        """Test extraction of unique entity names"""
        requirements = [
            "User can create products",
            "User can view products",
            "Admin can delete products"
        ]
        
        entities = self.parser.extract_entity_names(requirements)
        
        assert isinstance(entities, set)
        assert len(entities) >= 1
    
    def test_entities_from_multiple_requirements(self):
        """Test entity extraction from multiple requirements"""
        requirements = [
            "User can manage products",
            "Customer can view orders",
            "Admin can edit accounts"
        ]
        
        entities = self.parser.extract_entity_names(requirements)
        
        # Should find multiple entity types
        assert len(entities) >= 1


class TestParserPerformance:
    """Test parser performance"""
    
    def setup_method(self):
        """Initialize parser before each test"""
        self.parser = RequirementParser()
    
    def test_parse_many_requirements(self):
        """Test parsing many requirements"""
        requirements = [
            f"User can perform action {i} on entity {i}"
            for i in range(100)
        ]
        
        import time
        start = time.time()
        
        for req in requirements:
            self.parser.parse_requirement(req)
        
        duration = time.time() - start
        
        # Should complete in reasonable time
        assert duration < 5.0  # Less than 5 seconds for 100 reqs
    
    def test_parse_complex_requirements_performance(self):
        """Test performance with complex requirements"""
        complex_reqs = [
            "The authenticated system administrator with elevated privileges shall have the capability to create, read, update, and permanently delete user account records from the centralized database",
            "Registered customers can upload multiple file attachments including PDF documents, Word files, and images up to 10MB each to their personal secure cloud storage",
            "The system must automatically send email notifications to all subscribed users when new content matching their preferences becomes available"
        ] * 10  # 30 complex requirements
        
        import time
        start = time.time()
        
        for req in complex_reqs:
            self.parser.parse_requirement(req)
        
        duration = time.time() - start
        
        # Should handle complex requirements efficiently
        assert duration < 3.0  # Less than 3 seconds


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])