from __future__ import annotations
import os
from abc import ABC, abstractmethod
import requests


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, system_message: str, messages: list[dict[str, str]],
             temperature: float = 0.0) -> str: ...
    @property
    @abstractmethod
    def model_name(self) -> str: ...


class OpenAIProvider(LLMProvider):
    def __init__(self, model="gpt-4o", timeout=120):
        import openai
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY not set.")
        self._client = openai.OpenAI(api_key=api_key, timeout=timeout)
        self._model = model

    @property
    def model_name(self):
        return self._model

    def chat(self, system_message, messages, temperature=0.0):
        full = [{"role": "system", "content": system_message}] + messages
        r = self._client.chat.completions.create(
            model=self._model, messages=full, temperature=temperature)
        return r.choices[0].message.content or ""


class OllamaProvider(LLMProvider):
    def __init__(self, model="llama3.1:8b", timeout=120):
        api_key = os.getenv("OLLAMA_API_KEY")
        if not api_key:
            raise EnvironmentError("OLLAMA_API_KEY not set.")
        base_url = os.getenv("OLLAMA_BASE_URL", "https://genai-01.uni-hildesheim.de/ollama")
        self._model = model
        self.api_endpoint = f"{base_url}/api/chat"
        self.headers = {"Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}"}
        self.timeout = timeout

    @property
    def model_name(self):
        return self._model

    def chat(self, system_message, messages, temperature=0.0):
        full = [{"role": "system", "content": system_message}] + messages
        r = requests.post(
            self.api_endpoint, headers=self.headers,
            json={"model": self._model, "messages": full,
                  "options": {"temperature": temperature}, "stream": False},
            timeout=self.timeout)
        r.raise_for_status()
        return r.json()["message"]["content"] or ""


class StubProvider(LLMProvider):
    def __init__(self, responses=None):
        self._responses = responses or [
            "Thank you. Who are the primary users?",
            "What are the most important features?",
            "How quickly should it respond?",
            "How should users authenticate?",
            "What happens if the system goes offline?",
            "Is there anything else?",
        ]
        self._index = 0

    @property
    def model_name(self):
        return "stub-provider-v1"

    def chat(self, system_message, messages, temperature=0.0):
        r = self._responses[self._index % len(self._responses)]
        self._index += 1
        return r


def create_provider(name="ollama", **kwargs):
    if name == "openai":
        return OpenAIProvider(**kwargs)
    elif name == "ollama":
        return OllamaProvider(**kwargs)
    elif name == "stub":
        return StubProvider(**kwargs)
    raise ValueError(f"Unknown provider: {name!r}")