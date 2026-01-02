"""
OpenAI API Client for GPT-4-turbo Communication
Handles communication with OpenAI API for UML diagram generation
"""

import os
from typing import List, Dict, Optional
from openai import OpenAI


class OpenAIClient:
    """Client for interacting with OpenAI API"""
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        model: str = "gpt-4-turbo-preview",
        temperature: float = 0.7,
        fallback_model: str = "gpt-3.5-turbo"
    ):
        """
        Initialize OpenAI client
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Model name to use (default: gpt-4-turbo-preview)
            temperature: Default temperature for sampling
            fallback_model: Fallback model if primary fails
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key not provided. Set OPENAI_API_KEY environment variable.")
        
        self.model = model or os.getenv('OPENAI_MODEL', 'gpt-4-turbo-preview')
        self.temperature = float(os.getenv('OPENAI_TEMPERATURE', temperature))
        self.fallback_model = fallback_model or os.getenv('OPENAI_FALLBACK_MODEL', 'gpt-3.5-turbo')
        
        self.client = OpenAI(api_key=self.api_key)
    
    def chat(
        self, 
        messages: List[Dict[str, str]], 
        temperature: Optional[float] = None,
        model: Optional[str] = None
    ) -> str:
        """
        Send chat messages to OpenAI and get response
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (overrides default)
            model: Model name (overrides default)
        
        Returns:
            Assistant's response text
        """
        try:
            response = self.client.chat.completions.create(
                model=model or self.model,
                messages=messages,
                temperature=temperature if temperature is not None else self.temperature
            )
            
            return response.choices[0].message.content
        except Exception as e:
            # Try fallback model if primary fails
            if model != self.fallback_model:
                print(f"Error with {self.model}, trying fallback {self.fallback_model}: {str(e)}")
                try:
                    response = self.client.chat.completions.create(
                        model=self.fallback_model,
                        messages=messages,
                        temperature=temperature if temperature is not None else self.temperature
                    )
                    return response.choices[0].message.content
                except Exception as fallback_error:
                    print(f"Fallback model also failed: {str(fallback_error)}")
                    raise
            
            print(f"Error communicating with OpenAI: {str(e)}")
            raise
    
    def chat_with_system_prompt(
        self,
        system_prompt: str,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None
    ) -> str:
        """
        Chat with a system prompt and optional conversation history
        
        Args:
            system_prompt: System-level instruction for the model
            user_message: Current user message
            conversation_history: Previous messages (optional)
            temperature: Sampling temperature (overrides default)
        
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
        Check if OpenAI API is accessible
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self.client.models.list()
            return True
        except:
            return False

