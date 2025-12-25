"""
Integration tests for Flask /api/chat endpoint with Elicitation Agent

Tests the complete workflow from HTTP request to agent response.
"""

import pytest
import json
from unittest.mock import Mock, patch
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from src.agents.elicitation_agent import Artifact


class TestChatEndpointIntegration:
    """Integration tests for /api/chat endpoint."""
    
    @pytest.fixture
    def client(self):
        """Flask test client."""
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client
    
    @pytest.fixture
    def mock_openai_response(self):
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
    
    @patch('openai.ChatCompletion.create')
    def test_chat_endpoint_with_elicitation_agent(self, mock_create, client, mock_openai_response):
        """Test /api/chat endpoint with successful agent response."""
        mock_create.return_value = mock_openai_response
        
        # Send chat message
        response = client.post('/api/chat',
            data=json.dumps({
                "message": "Users should be able to borrow books",
                "session_id": "test-session-1",
                "project_description": "Library Management System"
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert "response" in data
        assert data["agent"] == "ElicitationAgent"
        
        # Verify artifact was created (message contains "should")
        assert data["artifact"] is not None
        assert data["artifact"]["content"] == "Users should be able to borrow books"
        assert data["artifact"]["created_by"] == "Elicitation_Agent"
        
        # Verify metadata
        assert "metadata" in data
        assert "usage" in data["metadata"]
        assert "usage_stats" in data
    
    @patch('openai.ChatCompletion.create')
    def test_chat_endpoint_conversation_continuity(self, mock_create, client, mock_openai_response):
        """Test that conversation history is maintained across multiple requests."""
        mock_create.return_value = mock_openai_response
        
        session_id = "test-session-2"
        
        # First message
        response1 = client.post('/api/chat',
            data=json.dumps({
                "message": "I'm building a library system",
                "session_id": session_id
            }),
            content_type='application/json'
        )
        assert response1.status_code == 200
        
        # Second message in same session
        response2 = client.post('/api/chat',
            data=json.dumps({
                "message": "Users should be able to search for books",
                "session_id": session_id
            }),
            content_type='application/json'
        )
        assert response2.status_code == 200
        
        # Verify session maintains artifacts
        data2 = json.loads(response2.data)
        assert data2["status"] == "success"
    
    def test_chat_endpoint_missing_message(self, client):
        """Test error handling for missing message."""
        response = client.post('/api/chat',
            data=json.dumps({"session_id": "test"}),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["status"] == "error"
        assert "No message provided" in data["message"]
    
    @patch('openai.ChatCompletion.create')
    def test_chat_endpoint_no_artifact_for_question(self, mock_create, client, mock_openai_response):
        """Test that questions don't create artifacts."""
        mock_create.return_value = mock_openai_response
        
        response = client.post('/api/chat',
            data=json.dumps({
                "message": "What features should I include?",
                "session_id": "test-session-3"
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["artifact"] is None
    
    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get('/api/health')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "healthy"
        assert "agents" in data
        assert "elicitation_agent" in data["agents"]
    
    def test_new_session_endpoint(self, client):
        """Test new session creation."""
        response = client.post('/api/new-session',
            data=json.dumps({"session_id": "new-test-session"}),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert data["session_id"] == "new-test-session"
    
    @patch('openai.ChatCompletion.create')
    def test_usage_stats_endpoint(self, mock_create, client, mock_openai_response):
        """Test usage statistics endpoint."""
        mock_create.return_value = mock_openai_response
        
        # Make a chat request first
        client.post('/api/chat',
            data=json.dumps({
                "message": "Users must login",
                "session_id": "stats-test"
            }),
            content_type='application/json'
        )
        
        # Get usage stats
        response = client.get('/api/usage-stats')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert "stats" in data
        assert "total_tokens" in data["stats"]
        assert "total_cost" in data["stats"]


class TestSpecGenerationIntegration:
    """Integration tests for SRS generation."""
    
    @pytest.fixture
    def client(self):
        """Flask test client."""
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client
    
    @patch('openai.ChatCompletion.create')
    def test_generate_spec_endpoint(self, mock_create, client):
        """Test SRS generation from elicited requirements."""
        # Mock response
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Follow-up question"))]
        mock_response.usage = Mock(prompt_tokens=100, completion_tokens=20, total_tokens=120)
        mock_create.return_value = mock_response
        
        session_id = "spec-test-session"
        
        # Elicit some requirements first
        client.post('/api/chat',
            data=json.dumps({
                "message": "Users should be able to borrow books",
                "session_id": session_id,
                "project_description": "Library System"
            }),
            content_type='application/json'
        )
        
        client.post('/api/chat',
            data=json.dumps({
                "message": "The system must track due dates",
                "session_id": session_id
            }),
            content_type='application/json'
        )
        
        # Generate spec
        response = client.post('/api/generate-spec',
            data=json.dumps({"session_id": session_id}),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert "specification" in data
        assert "SOFTWARE REQUIREMENTS SPECIFICATION" in data["specification"]
        assert data["artifacts_count"] >= 1
    
    def test_generate_spec_no_session(self, client):
        """Test error when generating spec for non-existent session."""
        response = client.post('/api/generate-spec',
            data=json.dumps({"session_id": "nonexistent"}),
            content_type='application/json'
        )
        
        assert response.status_code == 404
        data = json.loads(response.data)
        assert data["status"] == "error"
    
    def test_generate_spec_no_requirements(self, client):
        """Test error when generating spec without requirements."""
        # Create empty session
        client.post('/api/new-session',
            data=json.dumps({"session_id": "empty-session"}),
            content_type='application/json'
        )
        
        # Try to generate spec
        response = client.post('/api/generate-spec',
            data=json.dumps({"session_id": "empty-session"}),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["status"] == "error"
        assert "No requirements" in data["message"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
