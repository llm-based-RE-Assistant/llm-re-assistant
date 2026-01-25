"""
Unit tests for OpenAI Client
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from openai import OpenAI


class TestOpenAIClient:
    """Test cases for OpenAI API client"""
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key-123'})
    @patch('src.utils.openai_client.OpenAI')
    def test_initialization(self, mock_openai_class):
        """Test client initialization"""
        from src.utils.openai_client import OpenAIClient
        
        client = OpenAIClient()
        
        assert client.api_key == 'test-key-123'
        assert client.model is not None
        mock_openai_class.assert_called_once()
    
    @patch.dict(os.environ, {}, clear=True)
    def test_initialization_missing_key(self):
        """Test that missing API key raises error"""
        from src.utils.openai_client import OpenAIClient
        
        with pytest.raises(ValueError, match="API key"):
            OpenAIClient()
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key-123'})
    @patch('src.utils.openai_client.OpenAI')
    def test_chat_with_system_prompt(self, mock_openai_class):
        """Test chat with system prompt"""
        from src.utils.openai_client import OpenAIClient
        
        # Mock OpenAI response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated response"
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        client = OpenAIClient(api_key='test-key')
        
        response = client.chat_with_system_prompt(
            system_prompt="You are a helpful assistant",
            user_message="Hello"
        )
        
        assert response == "Generated response"
        mock_client.chat.completions.create.assert_called_once()
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key-123'})
    @patch('src.utils.openai_client.OpenAI')
    def test_chat_fallback_model(self, mock_openai_class):
        """Test fallback to GPT-3.5-turbo on error"""
        from src.utils.openai_client import OpenAIClient
        
        # Mock OpenAI to fail first, then succeed with fallback
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Fallback response"
        
        # First call fails, second succeeds
        mock_client.chat.completions.create.side_effect = [
            Exception("API Error"),
            mock_response
        ]
        mock_openai_class.return_value = mock_client
        
        client = OpenAIClient(api_key='test-key', model='gpt-4-turbo-preview')
        
        response = client.chat([
            {'role': 'user', 'content': 'Hello'}
        ])
        
        assert response == "Fallback response"
        # Should have been called twice (primary + fallback)
        assert mock_client.chat.completions.create.call_count == 2

