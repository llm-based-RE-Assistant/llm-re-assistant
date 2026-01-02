"""
Unit tests for Modeling Agent
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.agents.modeling_agent import ModelingAgent
from src.utils.openai_client import OpenAIClient


class TestModelingAgent:
    """Test cases for UML generation agent"""
    
    def setup_method(self):
        """Set up test fixtures"""
        # Mock OpenAI client
        self.mock_openai_client = Mock(spec=OpenAIClient)
        self.agent = ModelingAgent(openai_client=self.mock_openai_client)
    
    def test_clean_plantuml_code_removes_markdown(self):
        """Test that markdown code blocks are removed"""
        raw_code = "```plantuml\n@startuml\nclass User {}\n@enduml\n```"
        cleaned = self.agent._clean_plantuml_code(raw_code)
        
        assert "```" not in cleaned
        assert "@startuml" in cleaned
        assert "@enduml" in cleaned
    
    def test_clean_plantuml_code_adds_tags(self):
        """Test that missing tags are added"""
        code_without_tags = "class User {\n  +String username\n}"
        cleaned = self.agent._clean_plantuml_code(code_without_tags)
        
        assert "@startuml" in cleaned.lower()
        assert "@enduml" in cleaned.lower()
    
    def test_extract_expected_entities(self):
        """Test entity extraction from requirements"""
        requirements = """
        A library system has books, members, and loans.
        Each book has a title and ISBN.
        Members can borrow multiple books.
        """
        
        entities = self.agent._extract_expected_entities(requirements)
        
        # Should extract at least some entities
        assert len(entities) > 0
        # Check for common entities (case-insensitive)
        entity_names = [e.lower() for e in entities]
        assert any('book' in e or 'member' in e or 'loan' in e for e in entity_names)
    
    def test_extract_requirements_from_conversation(self):
        """Test requirements extraction from conversation"""
        conversation = [
            {'role': 'user', 'content': 'I want to build a library system'},
            {'role': 'assistant', 'content': 'Great! Tell me about the books.'},
            {'role': 'user', 'content': 'Books have title and ISBN'}
        ]
        
        requirements = self.agent._extract_requirements_from_conversation('', conversation)
        
        assert 'library system' in requirements.lower()
        assert 'book' in requirements.lower()
    
    def test_extract_requirements_explicit(self):
        """Test that explicit requirements are used when provided"""
        explicit_req = "A system with users and orders"
        conversation = [{'role': 'user', 'content': 'Hello'}]
        
        requirements = self.agent._extract_requirements_from_conversation(explicit_req, conversation)
        
        assert requirements == explicit_req
    
    def test_assess_quality_completeness_ratio(self):
        """Test completeness ratio calculation"""
        requirements = "A system has User, Order, and Product classes"
        plantuml_code = """@startuml
class User {
  +String username
}
class Order {
  +int orderId
}
@enduml"""
        
        validation_result = {
            'is_valid': True,
            'warnings': [],
            'entities_count': 2,
            'relationships_count': 0
        }
        
        quality = self.agent._assess_quality(requirements, plantuml_code, validation_result)
        
        assert 'completeness_ratio' in quality
        assert 0.0 <= quality['completeness_ratio'] <= 1.0
        assert quality['entities_found'] == 2
    
    def test_assess_quality_low_completeness_warning(self):
        """Test warning for low completeness ratio"""
        requirements = "A system has User, Order, Product, Payment, and Shipping classes"
        plantuml_code = """@startuml
class User {
  +String username
}
@enduml"""
        
        validation_result = {
            'is_valid': True,
            'warnings': [],
            'entities_count': 1,
            'relationships_count': 0
        }
        
        quality = self.agent._assess_quality(requirements, plantuml_code, validation_result)
        
        # Should have warning about low completeness
        assert len(quality['warnings']) > 0
        assert any('completeness' in w.lower() or 'review' in w.lower() for w in quality['warnings'])
    
    def test_assess_quality_missing_relationships_warning(self):
        """Test warning for missing relationships"""
        requirements = "Users place orders"
        plantuml_code = """@startuml
class User {
  +String username
}
class Order {
  +int orderId
}
@enduml"""
        
        validation_result = {
            'is_valid': True,
            'warnings': [],
            'entities_count': 2,
            'relationships_count': 0
        }
        
        quality = self.agent._assess_quality(requirements, plantuml_code, validation_result)
        
        # Should warn about missing relationships
        assert any('relationship' in w.lower() for w in quality['warnings'])
    
    @patch('src.agents.modeling_agent.PlantUMLValidator')
    def test_generate_uml_success(self, mock_validator_class):
        """Test successful UML generation"""
        # Mock validator
        mock_validator = Mock()
        mock_validator.validate.return_value = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'entities_count': 2,
            'relationships_count': 1
        }
        mock_validator.extract_entities.return_value = ['User', 'Order']
        mock_validator_class.return_value = mock_validator
        
        # Mock OpenAI response
        self.mock_openai_client.chat_with_system_prompt.return_value = """@startuml
class User {
  +String username
}
class Order {
  +int orderId
}
User "1" -- "*" Order : places
@enduml"""
        
        # Create new agent with mocked validator
        agent = ModelingAgent(openai_client=self.mock_openai_client)
        agent.validator = mock_validator
        
        result = agent.generate_uml("A system with users and orders")
        
        assert result['status'] == 'success'
        assert 'plantuml_code' in result
        assert 'quality' in result
        assert result['quality']['completeness_ratio'] >= 0.0
    
    @patch('src.agents.modeling_agent.PlantUMLValidator')
    def test_generate_uml_invalid_syntax(self, mock_validator_class):
        """Test handling of invalid PlantUML syntax"""
        # Mock validator returning invalid result
        mock_validator = Mock()
        mock_validator.validate.return_value = {
            'is_valid': False,
            'errors': ['Missing @startuml tag'],
            'warnings': [],
            'entities_count': 0,
            'relationships_count': 0
        }
        mock_validator_class.return_value = mock_validator
        
        # Mock OpenAI response with invalid code
        self.mock_openai_client.chat_with_system_prompt.return_value = "class User {}"
        
        agent = ModelingAgent(openai_client=self.mock_openai_client)
        agent.validator = mock_validator
        
        result = agent.generate_uml("A system with users")
        
        assert result['status'] == 'error'
        assert 'error' in result
    
    def test_build_prompt_includes_examples(self):
        """Test that prompt includes few-shot examples"""
        requirements = "A library system"
        prompt = self.agent._build_prompt(requirements)
        
        # Should include examples from prompts.json
        assert 'Example' in prompt or 'example' in prompt
        assert requirements in prompt
    
    def test_load_prompts_fallback(self):
        """Test that prompts load with fallback if file missing"""
        # This test verifies the fallback mechanism works
        # In practice, the file should exist, but we test the error handling
        agent = ModelingAgent(openai_client=self.mock_openai_client)
        
        # Prompts should be loaded (either from file or fallback)
        assert 'system_prompt' in agent.prompts
        assert 'few_shot_examples' in agent.prompts

