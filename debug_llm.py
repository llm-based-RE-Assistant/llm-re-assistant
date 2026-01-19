#!/usr/bin/env python3
"""Debug LLM connection"""

from src.utils.ollama_client import OllamaClient

print("="*70)
print("LLM CONNECTION DEBUG")
print("="*70)

client = OllamaClient()

print(f"\n1. Connection check: {client.check_connection()}")
print(f"2. Base URL: {client.base_url}")
print(f"3. Model: {client.model}")

# Try a simple test
print("\n4. Testing actual chat call...")
response = client.chat_with_system_prompt(
    system_prompt="You are a test assistant.",
    user_message="Say 'Hello, I am working!' in exactly 5 words.",
    temperature=0.0
)

print(f"\nResponse: {response}")

if "trouble connecting" in response.lower() or "error" in response.lower():
    print("\n❌ LLM NOT working - using fallback")
else:
    print("\n✅ LLM IS WORKING!")
