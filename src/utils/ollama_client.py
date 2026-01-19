# """
# Ollama API Client for LLM Communication
# Handles communication with locally hosted Ollama models
# """

# import requests, os, json
# from typing import List, Dict, Optional


# class OllamaClient:
#     """Client for interacting with Ollama API"""
    
#     def __init__(self, base_url: str = "https://genai-01.uni-hildesheim.de/ollama", model: str = "llama3.1:8b"):
#         """
#         Initialize Ollama client
        
#         Args:
#             base_url: Base URL for Ollama API
#             model: Model name to use (default: llama3.1:8b)
#         """
#         self.base_url = base_url
#         self.model = model
#         self.api_endpoint = f"{base_url}/api/chat"
#         self.headers = {
#             "Content-Type": "application/json",
#             "Authorization": f"Bearer {os.getenv("OLLAMA_API_KEY")}",
#         }
    
#     def chat(
#         self, 
#         messages: List[Dict[str, str]], 
#         temperature: float = 0.7,
#         stream: bool = False
#     ) -> str:
#         """
#         Send chat messages to Ollama and get response
        
#         Args:
#             messages: List of message dicts with 'role' and 'content'
#             temperature: Sampling temperature (0.0 to 1.0)
#             stream: Whether to stream the response
        
#         Returns:
#             Assistant's response text
#         """
#         try:
#             payload = {
#                 "model": self.model,
#                 "messages": messages,
#                 "stream": stream,
#                 "options": {
#                     "temperature": temperature
#                 }
#             }
            
#             response = requests.post(
#                 self.api_endpoint,
#                 headers=self.headers,
#                 json=payload,
#                 timeout=120
#             )
            
#             response.raise_for_status()
            
#             result = response.json()
#             return result.get('message', {}).get('content', '')
#         except requests.exceptions.RequestException as e:
#             print(f"Error communicating with Ollama: {str(e)}")
#             return "I apologize, but I'm having trouble connecting to the language model. Please ensure Ollama is running."
#         except Exception as e:
#             print(f"Unexpected error in chat: {str(e)}")
#             return "An unexpected error occurred. Please try again."
    
#     def chat_with_system_prompt(
#         self,
#         system_prompt: str,
#         user_message: str,
#         conversation_history: Optional[List[Dict[str, str]]] = None,
#         temperature: float = 0.7
#     ) -> str:
#         """
#         Chat with a system prompt and optional conversation history
        
#         Args:
#             system_prompt: System-level instruction for the model
#             user_message: Current user message
#             conversation_history: Previous messages (optional)
#             temperature: Sampling temperature
        
#         Returns:
#             Assistant's response text
#         """
#         messages = [{"role": "system", "content": system_prompt}]
        
#         # Add conversation history if provided
#         if conversation_history:
#             messages.extend(conversation_history)
        
#         # Add current user message
#         messages.append({"role": "user", "content": user_message})
        
#         return self.chat(messages, temperature=temperature)
    
#     def check_connection(self) -> bool:
#         """
#         Check if Ollama is running and accessible
        
#         Returns:
#             True if connection successful, False otherwise
#         """
#         try:
#             response = requests.get(f"{self.base_url}/api/tags", timeout=5)
#             return response.status_code == 200
#         except:
#             return False
"""
Ollama API Client for LLM Communication
Handles communication with locally hosted Ollama models
"""

import requests
import os
import json
from typing import List, Dict, Optional


class OllamaClient:
    """Client for interacting with Ollama API"""
    
    def __init__(
        self, 
        base_url: str = None,
        model: str = "llama3.1:8b"
    ):
        """
        Initialize Ollama client
        
        Args:
            base_url: Base URL for Ollama API (defaults to env var or default URL)
            model: Model name to use (default: llama3.1:8b)
        """
        self.base_url = base_url or os.getenv(
            "OLLAMA_BASE_URL",
            "https://genai-01.uni-hildesheim.de/ollama"
        )
        self.model = model
        self.api_endpoint = f"{self.base_url}/api/chat"
        
        # Get API key from environment
        api_key = os.getenv("OLLAMA_API_KEY")
        
        self.headers = {
            "Content-Type": "application/json",
        }
        
        # Only add Authorization header if API key exists
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        
        self._connection_verified = False
    
    def chat(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.7,
        stream: bool = False,
        max_retries: int = 2
    ) -> str:
        """
        Send chat messages to Ollama and get response
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0.0 to 1.0)
            stream: Whether to stream the response
            max_retries: Number of retry attempts on failure
        
        Returns:
            Assistant's response text
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature
            }
        }
        
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    self.api_endpoint,
                    headers=self.headers,
                    json=payload,
                    timeout=120
                )
                
                # Detailed error logging
                if response.status_code != 200:
                    error_detail = self._parse_error_response(response)
                    print(f"API Error (attempt {attempt + 1}/{max_retries + 1}):")
                    print(f"  Status: {response.status_code}")
                    print(f"  Detail: {error_detail}")
                    
                    if attempt < max_retries:
                        continue
                    
                    return f"API Error: {error_detail}"
                
                response.raise_for_status()
                
                result = response.json()
                content = result.get('message', {}).get('content', '')
                
                if content:
                    self._connection_verified = True
                    return content
                else:
                    print(f"Empty response from API (attempt {attempt + 1})")
                    if attempt < max_retries:
                        continue
                    return "Error: Empty response from language model"
                
            except requests.exceptions.Timeout as e:
                last_error = f"Request timeout: {str(e)}"
                print(f"Timeout (attempt {attempt + 1}/{max_retries + 1}): {last_error}")
                if attempt < max_retries:
                    continue
                    
            except requests.exceptions.ConnectionError as e:
                last_error = f"Connection failed: {str(e)}"
                print(f"Connection error (attempt {attempt + 1}/{max_retries + 1}): {last_error}")
                if attempt < max_retries:
                    continue
                    
            except requests.exceptions.RequestException as e:
                last_error = f"Request failed: {str(e)}"
                print(f"Request error (attempt {attempt + 1}/{max_retries + 1}): {last_error}")
                if attempt < max_retries:
                    continue
                    
            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                print(f"Unexpected error (attempt {attempt + 1}/{max_retries + 1}): {last_error}")
                if attempt < max_retries:
                    continue
        
        # All retries exhausted
        return f"Failed after {max_retries + 1} attempts. Last error: {last_error}"
    
    def _parse_error_response(self, response: requests.Response) -> str:
        """
        Parse error response from API
        
        Args:
            response: HTTP response object
            
        Returns:
            Human-readable error message
        """
        try:
            error_data = response.json()
            return error_data.get('error', response.text)
        except:
            return response.text[:200] if response.text else f"HTTP {response.status_code}"
    
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
        if self._connection_verified:
            return True
        
        try:
            # Try tags endpoint first
            response = requests.get(
                f"{self.base_url}/api/tags",
                headers=self.headers,
                timeout=5
            )
            
            if response.status_code == 200:
                self._connection_verified = True
                return True
            
            # Try a simple chat as fallback
            test_response = self.chat(
                messages=[{"role": "user", "content": "ping"}],
                temperature=0.0,
                max_retries=1
            )
            
            # Check if we got a real response (not an error message)
            if test_response and not test_response.startswith("Failed after"):
                self._connection_verified = True
                return True
            
            return False
            
        except Exception as e:
            print(f"Connection check failed: {e}")
            return False
    
    def get_model_info(self) -> Dict:
        """
        Get information about the current model
        
        Returns:
            Dictionary with model information or error
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/show",
                headers=self.headers,
                json={"name": self.model},
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}", "details": response.text[:200]}
                
        except Exception as e:
            return {"error": str(e)}