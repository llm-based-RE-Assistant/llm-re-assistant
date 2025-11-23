"""
Ollama API Client for LLM Communication
Handles communication with locally hosted Ollama models
"""

import requests, os, json
from typing import List, Dict, Optional


class OllamaClient:
    """Client for interacting with Ollama API"""
    
    def __init__(self, base_url: str = "https://genai-01.uni-hildesheim.de/ollama", model: str = "llama3.1:8b"):
        """
        Initialize Ollama client
        
        Args:
            base_url: Base URL for Ollama API
            model: Model name to use (default: llama3.1:8b)
        """
        self.base_url = base_url
        self.model = model
        self.api_endpoint = f"{base_url}/api/chat"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.getenv("OLLAMA_API_KEY")}",
        }
    
    def chat(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.7,
        stream: bool = False
    ) -> str:
        """
        Send chat messages to Ollama and get response
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0.0 to 1.0)
            stream: Whether to stream the response
        
        Returns:
            Assistant's response text
        """
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": stream,
                "options": {
                    "temperature": temperature
                }
            }
            
            response = requests.post(
                self.api_endpoint,
                headers=self.headers,
                json=payload,
                timeout=120
            )
            
            response.raise_for_status()
            
            result = response.json()
            return result.get('message', {}).get('content', '')
        except requests.exceptions.RequestException as e:
            print(f"Error communicating with Ollama: {str(e)}")
            return "I apologize, but I'm having trouble connecting to the language model. Please ensure Ollama is running."
        except Exception as e:
            print(f"Unexpected error in chat: {str(e)}")
            return "An unexpected error occurred. Please try again."
    
    def chat_with_system_prompt(
        self,
        system_prompt: str,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.7
    ) -> str:
        """
        Chat with a system prompt and optional conversation history
        
        Args:
            system_prompt: System-level instruction for the model
            user_message: Current user message
            conversation_history: Previous messages (optional)
            temperature: Sampling temperature
        
        Returns:
            Assistant's response text
        """
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history if provided
        if conversation_history:
            messages.extend(conversation_history)
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        return self.chat(messages, temperature=temperature)
    
    def check_connection(self) -> bool:
        """
        Check if Ollama is running and accessible
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False