"""
Unit tests for Elicitation Agent

Tests cover:
1. GPT-4 API integration with mocked responses
2. Chain-of-Thought prompt generation
3. Artifact creation with proper metadata
4. Token usage tracking
5. Error handling and retry logic
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agents.elicitation_agent import ElicitationAgent, Artifact


class TestElicitationAgent:
    """Test suite for ElicitationAgent class."""
    
    @pytest.fixture
    def mock_openai_response(self):
        """Fixture providing a mock OpenAI API response."""
        mock_response = Mock()
        mock_response.choices = [
            Mock(message=Mock(content="What type of users will interact with the library system?"))
        ]
        mock_response.usage = Mock(
            prompt_tokens=150,
            completion_tokens=25,
            total_tokens=175
        )
        return mock_response
    
    @pytest.fixture
    def agent(self):
        """Fixture providing an ElicitationAgent instance."""
        return ElicitationAgent(
            api_key="test-api-key",
            model="gpt-4",
            temperature=0.7
        )
    
    def test_initialization_with_api_key(self):
        """Test agent initialization with provided API key."""
        agent = ElicitationAgent(api_key="test-key")
        assert agent.api_key == "test-key"
        assert agent.model == "gpt-4"
        assert agent.temperature == 0.7
        assert agent.total_tokens == 0
        assert agent.total_cost == 0.0
    
    def test_initialization_from_env(self):
        """Test agent initialization from environment variable."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}):
            agent = ElicitationAgent()
            assert agent.api_key == "env-key"
    
    def test_initialization_without_api_key_raises_error(self):
        """Test that missing API key raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="OpenAI API key must be provided"):
                ElicitationAgent()
    
    def test_calculate_cost(self, agent):
        """Test token cost calculation."""
        cost = agent._calculate_cost(100, 50, "gpt-4")
        expected = (100 / 1000) * 0.03 + (50 / 1000) * 0.06
        assert cost == expected
        
        # Test GPT-3.5 pricing
        cost_35 = agent._calculate_cost(100, 50, "gpt-3.5-turbo")
        expected_35 = (100 / 1000) * 0.0015 + (50 / 1000) * 0.002
        assert cost_35 == expected_35
    
    @patch('openai.ChatCompletion.create')
    def test_call_gpt4_success(self, mock_create, agent, mock_openai_response):
        """Test successful GPT-4 API call."""
        mock_create.return_value = mock_openai_response
        
        messages = [{"role": "user", "content": "Test message"}]
        response, usage = agent._call_gpt4_with_retry(messages)
        
        assert response == "What type of users will interact with the library system?"
        assert usage["prompt_tokens"] == 150
        assert usage["completion_tokens"] == 25
        assert usage["total_tokens"] == 175
        assert "cost" in usage
        assert agent.total_tokens == 175
    
    @patch('openai.ChatCompletion.create')
    def test_call_gpt4_with_retry_on_rate_limit(self, mock_create, agent, mock_openai_response):
        """Test retry logic on rate limit error."""
        import openai
        
        # First call fails with rate limit, second succeeds
        mock_create.side_effect = [
            openai.error.RateLimitError("Rate limit exceeded"),
            mock_openai_response
        ]
        
        messages = [{"role": "user", "content": "Test"}]
        
        with patch('time.sleep'):  # Mock sleep to speed up test
            response, usage = agent._call_gpt4_with_retry(messages)
        
        assert response == "What type of users will interact with the library system?"
        assert mock_create.call_count == 2
    
    @patch('openai.ChatCompletion.create')
    def test_call_gpt4_fallback_model(self, mock_create, mock_openai_response):
        """Test fallback to alternative model on failure."""
        import openai
        
        agent = ElicitationAgent(
            api_key="test-key",
            model="gpt-4",
            fallback_model="gpt-3.5-turbo",
            max_retries=1
        )
        
        # Primary model fails, fallback succeeds
        mock_create.side_effect = [
            openai.error.APIError("API error"),
            mock_openai_response
        ]
        
        messages = [{"role": "user", "content": "Test"}]
        
        with patch('time.sleep'):
            response, usage = agent._call_gpt4_with_retry(messages)
        
        assert response == "What type of users will interact with the library system?"
        assert usage["model"] == "gpt-3.5-turbo"
    
    def test_format_conversation_history(self, agent):
        """Test conversation history formatting."""
        history = [
            {"role": "user", "content": "I want to build a library system"},
            {"role": "assistant", "content": "What features do you need?"},
            {"role": "user", "content": "Book borrowing and returns"}
        ]
        
        formatted = agent._format_conversation_history(history)
        
        assert "Turn 1 [user]" in formatted
        assert "Turn 2 [assistant]" in formatted
        assert "Turn 3 [user]" in formatted
        assert "library system" in formatted
    
    def test_format_conversation_history_empty(self, agent):
        """Test formatting empty conversation history."""
        formatted = agent._format_conversation_history([])
        assert formatted == "No previous conversation."
    
    def test_format_requirements(self, agent):
        """Test requirements formatting."""
        artifact1 = Artifact(
            artifact_id="REQ-1",
            content="Users should be able to borrow books",
            created_by="Elicitation_Agent",
            confidence_score=0.9,
            metadata={},
            created_at=datetime.utcnow().isoformat()
        )
        artifact2 = Artifact(
            artifact_id="REQ-2",
            content="System must track return dates",
            created_by="Elicitation_Agent",
            confidence_score=0.85,
            metadata={},
            created_at=datetime.utcnow().isoformat()
        )
        
        agent.artifacts = [artifact1, artifact2]
        formatted = agent._format_requirements(agent.artifacts)
        
        assert "Req-1: Users should be able to borrow books" in formatted
        assert "Req-2: System must track return dates" in formatted
    
    def test_analyze_incompleteness(self, agent):
        """Test 4W framework incompleteness analysis."""
        history = [
            {"role": "user", "content": "Users should be able to borrow books from the web platform"}
        ]
        artifacts = []
        
        analysis = agent._analyze_incompleteness(history, artifacts)
        
        assert analysis["who"] is True  # "users" detected
        assert analysis["what"] is True  # "borrow" detected (functional)
        assert analysis["where"] is True  # "web" detected
        # "when" might be False if not mentioned
    
    def test_is_requirement_statement(self, agent):
        """Test requirement detection heuristic."""
        assert agent._is_requirement_statement("Users should be able to login") is True
        assert agent._is_requirement_statement("The system must validate passwords") is True
        assert agent._is_requirement_statement("Hello, how are you?") is False
        assert agent._is_requirement_statement("What features do you need?") is False
    
    def test_create_artifact(self, agent):
        """Test artifact creation with proper metadata."""
        artifact = agent._create_artifact(
            content="Users should be able to search for books",
            source_turn=3,
            session_id="test-session",
            confidence_score=0.95
        )
        
        assert artifact.content == "Users should be able to search for books"
        assert artifact.created_by == "Elicitation_Agent"
        assert artifact.confidence_score == 0.95
        assert artifact.metadata["source_turn"] == 3
        assert artifact.metadata["session_id"] == "test-session"
        assert artifact.metadata["stakeholder"] == "user"
        assert "REQ-test-session" in artifact.artifact_id
    
    @patch('openai.ChatCompletion.create')
    def test_elicit_requirements_integration(self, mock_create, agent, mock_openai_response):
        """Test full elicit_requirements workflow."""
        mock_create.return_value = mock_openai_response
        
        user_message = "Users should be able to borrow books for 2 weeks"
        conversation_history = []
        project_description = "Library Management System"
        
        response, artifact, metadata = agent.elicit_requirements(
            user_message=user_message,
            conversation_history=conversation_history,
            project_description=project_description,
            session_id="test-123"
        )
        
        # Verify response
        assert isinstance(response, str)
        assert len(response) > 0
        
        # Verify artifact was created (contains "should")
        assert artifact is not None
        assert artifact.content == user_message
        assert artifact.metadata["session_id"] == "test-123"
        
        # Verify metadata
        assert metadata["turn"] == 1
        assert metadata["artifact_created"] is True
        assert "incompleteness_analysis" in metadata
        assert "usage" in metadata
    
    @patch('openai.ChatCompletion.create')
    def test_elicit_requirements_no_artifact_for_question(self, mock_create, agent, mock_openai_response):
        """Test that questions don't create artifacts."""
        mock_create.return_value = mock_openai_response
        
        user_message = "What are the main features?"
        conversation_history = []
        
        response, artifact, metadata = agent.elicit_requirements(
            user_message=user_message,
            conversation_history=conversation_history
        )
        
        # No artifact should be created for questions
        assert artifact is None
        assert metadata["artifact_created"] is False
    
    def test_get_artifacts(self, agent):
        """Test retrieving all artifacts."""
        artifact1 = agent._create_artifact("Requirement 1", 1, "test")
        artifact2 = agent._create_artifact("Requirement 2", 2, "test")
        
        agent.artifacts = [artifact1, artifact2]
        artifacts_dict = agent.get_artifacts()
        
        assert len(artifacts_dict) == 2
        assert artifacts_dict[0]["content"] == "Requirement 1"
        assert artifacts_dict[1]["content"] == "Requirement 2"
    
    @patch('openai.ChatCompletion.create')
    def test_get_usage_stats(self, mock_create, agent, mock_openai_response):
        """Test token usage statistics."""
        mock_create.return_value = mock_openai_response
        
        # Make a few elicitation calls
        for i in range(3):
            agent.elicit_requirements(
                user_message=f"Users should be able to {i}",
                conversation_history=[]
            )
        
        stats = agent.get_usage_stats()
        
        assert stats["total_tokens"] > 0
        assert stats["total_cost"] > 0
        assert stats["total_turns"] == 3
        assert stats["artifacts_created"] == 3
        assert "average_cost_per_turn" in stats
    
    def test_reset(self, agent):
        """Test agent reset functionality."""
        # Add some state
        agent.conversation_turn = 5
        agent.artifacts = [
            agent._create_artifact("Test", 1, "test")
        ]
        
        agent.reset()
        
        assert agent.conversation_turn == 0
        assert len(agent.artifacts) == 0
        # Token tracking persists across resets
        assert agent.total_tokens >= 0


class TestCoTPromptGeneration:
    """Test Chain-of-Thought prompt generation."""
    
    @pytest.fixture
    def agent(self):
        return ElicitationAgent(api_key="test-key")
    
    def test_cot_template_contains_required_sections(self, agent):
        """Test that CoT template has all required sections."""
        template = agent.COT_TEMPLATE
        
        assert "Think step-by-step" in template
        assert "UNDERSTAND" in template
        assert "IDENTIFY" in template
        assert "PROBE" in template
        assert "CLARIFY" in template
        assert "4W Framework" in template
        assert "WHO" in template
        assert "WHAT" in template
        assert "WHEN" in template
        assert "WHERE" in template
    
    @patch('openai.ChatCompletion.create')
    def test_cot_prompt_injection(self, mock_create, agent, mock_openai_response):
        """Test that context variables are properly injected into CoT prompt."""
        mock_create.return_value = mock_openai_response
        
        user_message = "I need user authentication"
        project_description = "Banking Application"
        conversation_history = [
            {"role": "user", "content": "I'm building a banking app"}
        ]
        
        # Capture the actual call to OpenAI
        agent.elicit_requirements(
            user_message=user_message,
            conversation_history=conversation_history,
            project_description=project_description
        )
        
        # Get the actual prompt sent
        call_args = mock_create.call_args
        messages = call_args[1]["messages"]
        user_prompt = messages[1]["content"]
        
        # Verify context injection
        assert project_description in user_prompt
        assert user_message in user_prompt
        assert "banking app" in user_prompt  # From history


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
