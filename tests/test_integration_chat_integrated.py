"""
Integration tests for Flask /api/chat endpoint with Elicitation Agent
Compatible with existing Iteration 1 infrastructure (ConversationManager, OllamaClient)

Tests both Iteration 1 (Ollama) and Iteration 2 (GPT-4) agents
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response."""
    mock_response = Mock()
    mock_response.choices = [
        Mock(message=Mock(content="What type of users will use this library system?"))
    ]
    mock_response.usage = Mock(
        prompt_tokens=150,
        completion_tokens=25,
        total_tokens=175
    )
    return mock_response


@pytest.fixture
def mock_ollama_response():
    """Mock Ollama API response."""
    return "What are the main features you need for your library system?"


class TestChatEndpointIntegrated:
    """Integration tests for /api/chat endpoint with both agents."""
    
    @pytest.fixture
    def client(self):
        """Flask test client with Iteration 2 enabled."""
        # Set environment for GPT-4 agent
        with patch.dict(os.environ, {
            'USE_GPT4_AGENT': 'true',
            'OPENAI_API_KEY': 'test-key',
            'SECRET_KEY': 'test-secret'
        }):
            # Import app after setting env vars
            from app_integrated import app
            app.config['TESTING'] = True
            with app.test_client() as client:
                yield client
    
    @pytest.fixture
    def client_v1(self):
        """Flask test client with Iteration 1 (Ollama only)."""
        with patch.dict(os.environ, {
            'USE_GPT4_AGENT': 'false',
            'SECRET_KEY': 'test-secret'
        }):
            from app_integrated import app
            app.config['TESTING'] = True
            with app.test_client() as client:
                yield client
    
    @patch('openai.ChatCompletion.create')
    def test_chat_with_gpt4_agent(self, mock_openai, client, mock_openai_response):
        """Test /api/chat with GPT-4 agent (Iteration 2)."""
        mock_openai.return_value = mock_openai_response
        
        with client.session_transaction() as sess:
            # Session will be auto-created by app
            pass
        
        # Send chat message
        response = client.post('/api/chat',
            data=json.dumps({
                "message": "Users should be able to borrow books"
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert "response" in data
        assert data["agent"] == "ElicitationAgent_v2_GPT4"
        assert data["iteration"] == 2
        
        # Verify artifact was created (message contains "should")
        if data.get("artifact"):
            assert data["artifact"]["content"] == "Users should be able to borrow books"
        
        # Verify metadata includes token usage
        assert "metadata" in data
        assert "usage_stats" in data
    
    @patch('src.utils.ollama_client.OllamaClient.chat_with_system_prompt')
    def test_chat_with_ollama_fallback(self, mock_ollama, client_v1, mock_ollama_response):
        """Test /api/chat with Ollama agent (Iteration 1 fallback)."""
        mock_ollama.return_value = mock_ollama_response
        
        # Send chat message
        response = client_v1.post('/api/chat',
            data=json.dumps({
                "message": "I want to build a library system"
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert "response" in data
        assert data["agent"] == "ElicitationEngine_v1_Ollama"
        assert data["iteration"] == 1
    
    @patch('openai.ChatCompletion.create')
    def test_conversation_persistence_with_conversation_manager(
        self, 
        mock_openai, 
        client, 
        mock_openai_response
    ):
        """Test that conversation is properly saved via ConversationManager."""
        mock_openai.return_value = mock_openai_response
        
        # First message
        response1 = client.post('/api/chat',
            data=json.dumps({
                "message": "I'm building a library system"
            }),
            content_type='application/json'
        )
        assert response1.status_code == 200
        
        # Second message in same session (session cookie maintained by test client)
        response2 = client.post('/api/chat',
            data=json.dumps({
                "message": "Users should be able to search for books"
            }),
            content_type='application/json'
        )
        assert response2.status_code == 200
        
        # Verify both messages processed
        data2 = json.loads(response2.data)
        assert data2["status"] == "success"
    
    def test_missing_message_error(self, client):
        """Test error handling for missing message."""
        response = client.post('/api/chat',
            data=json.dumps({}),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["status"] == "error"
        assert "Please provide a message" in data["response"]
    
    @patch('openai.ChatCompletion.create')
    def test_artifact_stored_in_conversation_manager(
        self, 
        mock_openai, 
        client, 
        mock_openai_response
    ):
        """Test that artifacts are stored in ConversationManager.add_requirement()."""
        mock_openai.return_value = mock_openai_response
        
        response = client.post('/api/chat',
            data=json.dumps({
                "message": "The system must authenticate users"
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # If artifact created, verify structure
        if data.get("artifact"):
            artifact = data["artifact"]
            assert "id" in artifact
            assert "content" in artifact
            assert "confidence" in artifact
            assert "metadata" in artifact


class TestSpecGenerationIntegrated:
    """Integration tests for SRS generation."""
    
    @pytest.fixture
    def client(self):
        """Flask test client."""
        with patch.dict(os.environ, {'SECRET_KEY': 'test-secret'}):
            from app_integrated import app
            app.config['TESTING'] = True
            with app.test_client() as client:
                yield client
    
    @patch('src.utils.ollama_client.OllamaClient.chat_with_system_prompt')
    def test_generate_spec_uses_existing_engine(self, mock_ollama, client):
        """Test that SRS generation uses existing Iteration 1 engine."""
        mock_ollama.return_value = "Mocked conversation response"
        
        # First, have a conversation
        client.post('/api/chat',
            data=json.dumps({
                "message": "I want to build a library system"
            }),
            content_type='application/json'
        )
        
        mock_ollama.return_value = """# SOFTWARE REQUIREMENTS SPECIFICATION
## 1. INTRODUCTION
### 1.1 Purpose
This document specifies requirements for a library management system."""
        
        # Generate spec
        response = client.post('/api/generate-spec',
            data=json.dumps({}),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert "SOFTWARE REQUIREMENTS SPECIFICATION" in data["specification"]
        assert "filename" in data
        assert data["filename"].startswith("artifacts/specifications/")


class TestSessionManagement:
    """Test session management with existing ConversationManager."""
    
    @pytest.fixture
    def client(self):
        """Flask test client."""
        with patch.dict(os.environ, {'SECRET_KEY': 'test-secret'}):
            from app_integrated import app
            app.config['TESTING'] = True
            with app.test_client() as client:
                yield client
    
    def test_new_session_creates_conversation_manager_session(self, client):
        """Test that new session uses ConversationManager."""
        response = client.post('/api/new-session',
            data=json.dumps({}),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert "session_id" in data
        assert "agent" in data
    
    @patch('src.utils.ollama_client.OllamaClient.chat_with_system_prompt')
    def test_session_info_endpoint(self, mock_ollama, client):
        """Test session info endpoint with ConversationManager integration."""
        mock_ollama.return_value = "Test response"
        
        # Create conversation
        client.post('/api/chat',
            data=json.dumps({
                "message": "Test message"
            }),
            content_type='application/json'
        )
        
        # Get session info
        response = client.get('/api/session-info')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert "session" in data
        assert data["session"]["message_count"] >= 2  # user + assistant


class TestHealthAndStats:
    """Test health check and usage stats endpoints."""
    
    @pytest.fixture
    def client_gpt4(self):
        """Client with GPT-4 enabled."""
        with patch.dict(os.environ, {
            'USE_GPT4_AGENT': 'true',
            'OPENAI_API_KEY': 'test-key',
            'SECRET_KEY': 'test-secret'
        }):
            from app_integrated import app
            app.config['TESTING'] = True
            with app.test_client() as client:
                yield client
    
    @pytest.fixture
    def client_ollama(self):
        """Client with only Ollama."""
        with patch.dict(os.environ, {
            'USE_GPT4_AGENT': 'false',
            'SECRET_KEY': 'test-secret'
        }):
            from app_integrated import app
            app.config['TESTING'] = True
            with app.test_client() as client:
                yield client
    
    def test_health_check_shows_both_agents(self, client_gpt4):
        """Test health check reports both agent statuses."""
        response = client_gpt4.get('/api/health')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "healthy"
        assert "agents" in data
        assert "ollama_v1" in data["agents"]
        assert "gpt4_v2" in data["agents"]
        assert data["iteration"] == 2
    
    @patch('openai.ChatCompletion.create')
    def test_usage_stats_with_gpt4(self, mock_openai, client_gpt4):
        """Test usage stats endpoint with GPT-4 agent."""
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Response"))]
        mock_response.usage = Mock(prompt_tokens=100, completion_tokens=20, total_tokens=120)
        mock_openai.return_value = mock_response
        
        # Make a request to accumulate stats
        client_gpt4.post('/api/chat',
            data=json.dumps({"message": "Test"}),
            content_type='application/json'
        )
        
        # Get stats
        response = client_gpt4.get('/api/usage-stats')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert "stats" in data
        assert data["agent"] == "GPT4_ElicitationAgent_v2"
    
    def test_usage_stats_unavailable_with_ollama(self, client_ollama):
        """Test that usage stats are unavailable with Ollama-only setup."""
        response = client_ollama.get('/api/usage-stats')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "unavailable"
        assert "only available with GPT-4" in data["message"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
