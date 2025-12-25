"""
Elicitation Agent for Requirements Engineering Assistant
Iteration 2 - Multi-Agent Architecture

This module implements a specialized agent for requirements elicitation using GPT-4
with Chain-of-Thought prompting and adaptive questioning strategies.

Scientific Justification:
- GPT-4 achieves 90-95% accuracy for conversational elicitation (Paper [2])
- CoT prompting improves performance by 15-20% over generic prompts (Paper [26])
- Multi-agent approach from Paper [28] achieved 0.98 completeness score

References:
- Paper [2]: Investigating ChatGPT's Potential in Requirements Elicitation
- Paper [26]: Graph-RAG with ToT prompting
- Paper [28]: MARE Multi-Agent Framework
"""

import os
import json
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import openai


@dataclass
class Artifact:
    """
    Represents an elicited requirement artifact with metadata.
    
    Attributes:
        artifact_id: Unique identifier for the artifact
        content: The elicited requirement text
        created_by: Agent that created this artifact
        confidence_score: Confidence level (0.0-1.0)
        metadata: Additional context (source_turn, stakeholder, etc.)
        created_at: Timestamp of creation
    """
    artifact_id: str
    content: str
    created_by: str
    confidence_score: float
    metadata: Dict
    created_at: str


class ElicitationAgent:
    """
    Specialized agent for requirements elicitation using GPT-4 with Chain-of-Thought prompting.
    
    This agent implements:
    1. GPT-4 API integration with error handling and retry logic
    2. Chain-of-Thought (CoT) prompt pattern for adaptive reasoning
    3. Adaptive questioning using 4W framework (Who, What, When, Where)
    4. Artifact creation with metadata tracking
    5. Token usage monitoring for cost tracking
    
    Example:
        >>> agent = ElicitationAgent(api_key="your-key", model="gpt-4")
        >>> response, artifact = agent.elicit_requirements(
        ...     user_message="I want to build a library management system",
        ...     conversation_history=[],
        ...     project_description="Library system for university"
        ... )
    """
    
    # Chain-of-Thought prompt template based on scientific design principles
    COT_TEMPLATE = """You are an expert Requirements Engineer conducting an elicitation interview.
    

    Think step-by-step:
    1. UNDERSTAND: What is the user trying to accomplish?
    2. IDENTIFY: Core entities and actions
    3. PROBE: Constraints or conditions
    4. CLARIFY: Edge cases and missing details

    Context:
    - Project Description: {project_description}
    - Conversation History: {conversation_history}
    - Current Draft Requirements: {current_requirements}

    4W Framework Analysis:
    - WHO: Which stakeholders/users are involved?
    - WHAT: What functionality is needed?
    - WHEN: What triggers or timing constraints exist?
    - WHERE: What is the deployment/usage context?

    User's Latest Message: {user_message}

    Based on your analysis, ask the MOST important follow-up question to elicit complete requirements.
    Focus on identifying missing information using the 4W framework.

    Your response should be conversational and focused on ONE key aspect at a time."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4",
        temperature: float = 0.7,
        max_retries: int = 3,
        fallback_model: Optional[str] = None
    ):
        """
        Initialize the Elicitation Agent.
        
        Args:
            api_key: OpenAI API key (reads from OPENAI_API_KEY env var if not provided)
            model: Model to use (default: gpt-4)
            temperature: Sampling temperature (0.0-1.0, default: 0.7)
            max_retries: Maximum retry attempts on API failures
            fallback_model: Fallback model if primary fails (e.g., "gpt-3.5-turbo")
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key must be provided or set in OPENAI_API_KEY environment variable")
        
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.fallback_model = fallback_model
        
        # Initialize OpenAI client
        openai.api_key = self.api_key
        
        # Token usage tracking
        self.total_tokens = 0
        self.total_cost = 0.0
        self.token_costs = {
            "gpt-4": {"prompt": 0.03, "completion": 0.06},  # per 1K tokens
            "gpt-4-turbo-preview": {"prompt": 0.01, "completion": 0.03},
            "gpt-3.5-turbo": {"prompt": 0.0015, "completion": 0.002}
        }
        
        # Conversation tracking
        self.artifacts: List[Artifact] = []
        self.conversation_turn = 0
    
    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int, model: str) -> float:
        """Calculate API call cost based on token usage."""
        if model not in self.token_costs:
            return 0.0
        
        costs = self.token_costs[model]
        prompt_cost = (prompt_tokens / 1000) * costs["prompt"]
        completion_cost = (completion_tokens / 1000) * costs["completion"]
        return prompt_cost + completion_cost
    
    def _call_gpt4_with_retry(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None
    ) -> Tuple[str, Dict]:
        """
        Call GPT-4 API with retry logic and error handling.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: Model to use (uses self.model if not specified)
        
        Returns:
            Tuple of (response_text, usage_stats)
        
        Raises:
            Exception: If all retry attempts fail
        """
        model = model or self.model
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                response = openai.ChatCompletion.create(
                    model=model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=500  # Limit response length for focused questions
                )
                
                # Extract response and usage
                response_text = response.choices[0].message.content
                usage = response.usage
                
                # Track token usage
                prompt_tokens = usage.prompt_tokens
                completion_tokens = usage.completion_tokens
                total_tokens = usage.total_tokens
                
                self.total_tokens += total_tokens
                cost = self._calculate_cost(prompt_tokens, completion_tokens, model)
                self.total_cost += cost
                
                usage_stats = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "cost": cost,
                    "model": model
                }
                
                return response_text, usage_stats
            
            except openai.error.RateLimitError as e:
                last_exception = e
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"Rate limit hit. Retrying in {wait_time}s... (Attempt {attempt + 1}/{self.max_retries})")
                time.sleep(wait_time)
            
            except openai.error.APIError as e:
                last_exception = e
                print(f"API error: {e}. Retrying... (Attempt {attempt + 1}/{self.max_retries})")
                time.sleep(1)
            
            except Exception as e:
                last_exception = e
                print(f"Unexpected error: {e}")
                break
        
        # Try fallback model if available
        if self.fallback_model and model != self.fallback_model:
            print(f"Trying fallback model: {self.fallback_model}")
            try:
                return self._call_gpt4_with_retry(messages, model=self.fallback_model)
            except Exception as fallback_error:
                print(f"Fallback model also failed: {fallback_error}")
        
        raise Exception(f"Failed to get response after {self.max_retries} attempts: {last_exception}")
    
    def _format_conversation_history(self, conversation_history: List[Dict]) -> str:
        """Format conversation history for prompt injection."""
        if not conversation_history:
            return "No previous conversation."
        
        formatted = []
        for i, turn in enumerate(conversation_history[-5:], 1):  # Last 5 turns only
            role = turn.get("role", "user")
            content = turn.get("content", "")
            formatted.append(f"Turn {i} [{role}]: {content}")
        
        return "\n".join(formatted)
    
    def _format_requirements(self, artifacts: List[Artifact]) -> str:
        """Format current requirements for prompt injection."""
        if not artifacts:
            return "No requirements elicited yet."
        
        formatted = []
        for i, artifact in enumerate(artifacts[-10:], 1):  # Last 10 artifacts
            formatted.append(f"Req-{i}: {artifact.content}")
        
        return "\n".join(formatted)
    
    def _analyze_incompleteness(
        self,
        conversation_history: List[Dict],
        artifacts: List[Artifact]
    ) -> Dict[str, bool]:
        """
        Analyze conversation using 4W framework to identify missing information.
        
        Returns:
            Dictionary with 4W analysis: {'who': bool, 'what': bool, 'when': bool, 'where': bool}
            True = information present, False = missing
        """
        # Simple keyword-based heuristic (can be enhanced with NLP)
        conversation_text = " ".join([turn.get("content", "") for turn in conversation_history])
        requirements_text = " ".join([art.content for art in artifacts])
        combined_text = (conversation_text + " " + requirements_text).lower()
        
        analysis = {
            "who": any(keyword in combined_text for keyword in ["user", "stakeholder", "admin", "customer", "client"]),
            "what": any(keyword in combined_text for keyword in ["function", "feature", "capability", "should", "must"]),
            "when": any(keyword in combined_text for keyword in ["when", "trigger", "schedule", "timing", "after", "before"]),
            "where": any(keyword in combined_text for keyword in ["platform", "system", "environment", "web", "mobile", "cloud"])
        }
        
        return analysis
    
    def elicit_requirements(
        self,
        user_message: str,
        conversation_history: List[Dict],
        project_description: str = "",
        session_id: str = ""
    ) -> Tuple[str, Optional[Artifact], Dict]:
        """
        Main elicitation method - analyzes user input and generates adaptive follow-up questions.
        
        Args:
            user_message: Latest message from the user
            conversation_history: List of previous conversation turns
            project_description: High-level project description
            session_id: Session identifier for tracking
        
        Returns:
            Tuple of (response_text, artifact_if_created, metadata)
            
        Example:
            >>> response, artifact, meta = agent.elicit_requirements(
            ...     user_message="Users should be able to borrow books",
            ...     conversation_history=[],
            ...     project_description="Library Management System"
            ... )
        """
        self.conversation_turn += 1
        
        # Analyze incompleteness using 4W framework
        incompleteness = self._analyze_incompleteness(conversation_history, self.artifacts)
        
        # Build Chain-of-Thought prompt
        formatted_history = self._format_conversation_history(conversation_history)
        formatted_requirements = self._format_requirements(self.artifacts)
        
        prompt = self.COT_TEMPLATE.format(
            project_description=project_description or "Not specified yet",
            conversation_history=formatted_history,
            current_requirements=formatted_requirements,
            user_message=user_message
        )
        
        # Prepare messages for GPT-4
        messages = [
            {
                "role": "system",
                "content": "You are an expert Requirements Engineer specializing in elicitation through adaptive questioning."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        # Call GPT-4
        try:
            response_text, usage_stats = self._call_gpt4_with_retry(messages)
        except Exception as e:
            return f"I apologize, but I'm having trouble processing your request: {str(e)}", None, {}
        
        # Check if we should create an artifact (requirement detected)
        artifact = None
        if self._is_requirement_statement(user_message):
            artifact = self._create_artifact(
                content=user_message,
                source_turn=self.conversation_turn,
                session_id=session_id
            )
            self.artifacts.append(artifact)
        
        # Prepare metadata
        metadata = {
            "turn": self.conversation_turn,
            "incompleteness_analysis": incompleteness,
            "usage": usage_stats,
            "artifact_created": artifact is not None
        }
        
        return response_text, artifact, metadata
    
    def _is_requirement_statement(self, text: str) -> bool:
        """
        Heuristic to detect if text contains a requirement statement.
        
        Can be enhanced with NLP classification or LLM-based detection.
        """
        text_lower = text.lower()
        requirement_keywords = ["should", "must", "shall", "need to", "require", "want to", "has to"]
        return any(keyword in text_lower for keyword in requirement_keywords)
    
    def _create_artifact(
        self,
        content: str,
        source_turn: int,
        session_id: str = "",
        confidence_score: float = 0.8
    ) -> Artifact:
        """
        Create an artifact with metadata for the shared workspace.
        
        Args:
            content: The requirement text
            source_turn: Conversation turn number
            session_id: Session identifier
            confidence_score: Confidence level (0.0-1.0)
        
        Returns:
            Artifact object with complete metadata
        """
        artifact_id = f"REQ-{session_id}-{len(self.artifacts) + 1}-{int(time.time())}"
        
        artifact = Artifact(
            artifact_id=artifact_id,
            content=content,
            created_by="Elicitation_Agent",
            confidence_score=confidence_score,
            metadata={
                "source_turn": source_turn,
                "stakeholder": "user",  # Can be enhanced to detect stakeholder
                "session_id": session_id,
                "elicitation_method": "conversational"
            },
            created_at=datetime.utcnow().isoformat()
        )
        
        return artifact
    
    def get_artifacts(self) -> List[Dict]:
        """
        Retrieve all artifacts created during elicitation.
        
        Returns:
            List of artifact dictionaries
        """
        return [asdict(artifact) for artifact in self.artifacts]
    
    def get_usage_stats(self) -> Dict:
        """
        Get token usage and cost statistics.
        
        Returns:
            Dictionary with total_tokens, total_cost, average_cost_per_turn
        """
        return {
            "total_tokens": self.total_tokens,
            "total_cost": round(self.total_cost, 4),
            "total_turns": self.conversation_turn,
            "average_cost_per_turn": round(self.total_cost / max(self.conversation_turn, 1), 4),
            "artifacts_created": len(self.artifacts)
        }
    
    def reset(self):
        """Reset agent state for new conversation session."""
        self.artifacts = []
        self.conversation_turn = 0
        # Note: Token usage is cumulative across sessions for cost tracking
