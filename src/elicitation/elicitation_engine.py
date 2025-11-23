"""
Elicitation Engine - Core logic for requirements elicitation
Implements Chain-of-Thought prompting and adaptive questioning
"""

from typing import List, Dict
from src.utils.ollama_client import OllamaClient


class ElicitationEngine:
    """Handles requirements elicitation through conversational interaction"""
    
    # System prompt for RE Assistant (inspired by papers [2][4][28])
    SYSTEM_PROMPT = """You are an expert Requirements Engineering Assistant with deep knowledge of software requirements elicitation, IEEE-830 standards, and the Volere requirements template.

Your role is to help stakeholders articulate their software requirements through natural, adaptive conversation. Follow these principles:

1. **Active Listening**: Carefully analyze each response to understand the stakeholder's needs
2. **Adaptive Questioning**: Ask follow-up questions to clarify vague or incomplete information
3. **4W Analysis**: Ensure you understand WHO, WHAT, WHEN, and WHERE for each requirement
4. **Ambiguity Detection**: Identify unclear statements and ask for clarification
5. **Completeness Checking**: Proactively identify missing information

When eliciting requirements:
- Start by understanding the project context and goals
- Ask open-ended questions to encourage detailed responses
- Break down complex ideas into specific, testable requirements
- Distinguish between functional and non-functional requirements
- Validate understanding by summarizing what you've learned

Be conversational, professional, and patient. Guide the stakeholder through the elicitation process step by step."""

    SPECIFICATION_GENERATION_PROMPT = """Based on the conversation history provided, generate a Software Requirements Specification (SRS) document following the IEEE-830 standard structure.

Structure your output as follows:

# SOFTWARE REQUIREMENTS SPECIFICATION

## 1. INTRODUCTION
### 1.1 Purpose
[Describe the purpose of this SRS and its intended audience]

### 1.2 Scope
[Define the scope of the software system, including main features and benefits]

### 1.3 Definitions, Acronyms, and Abbreviations
[List any technical terms, acronyms, or abbreviations used]

### 1.4 Overview
[Provide an overview of the rest of the document]

## 2. OVERALL DESCRIPTION
### 2.1 Product Perspective
[Describe how the system fits into the larger context]

### 2.2 Product Functions
[Summarize the major functions the software will perform]

### 2.3 User Characteristics
[Describe the intended users and their characteristics]

### 2.4 Constraints
[List any limitations or constraints]

### 2.5 Assumptions and Dependencies
[State any assumptions made and external dependencies]

## 3. FUNCTIONAL REQUIREMENTS
[List all functional requirements identified during elicitation]
Format: FR-X: [Requirement description]

## 4. NON-FUNCTIONAL REQUIREMENTS
### 4.1 Performance Requirements
[List performance-related requirements]

### 4.2 Security Requirements
[List security-related requirements]

### 4.3 Usability Requirements
[List usability-related requirements]

### 4.4 Other Non-Functional Requirements
[List any other non-functional requirements]

## 5. APPENDICES
[Include any additional information, diagrams, or references]

---
Extract specific requirements from the conversation and organize them clearly. Be precise and avoid ambiguity."""

    def __init__(self, ollama_client: OllamaClient):
        """
        Initialize elicitation engine
        
        Args:
            ollama_client: Initialized Ollama client for LLM communication
        """
        self.ollama_client = ollama_client
    
    def process_message(
        self, 
        user_message: str, 
        conversation_history: List[Dict[str, str]]
    ) -> str:
        """
        Process user message and generate appropriate response
        
        Args:
            user_message: Current message from user
            conversation_history: Previous conversation messages
        
        Returns:
            Assistant's response
        """
        # Prepare conversation history for LLM (role + content only)
        llm_history = [
            {'role': msg['role'], 'content': msg['content']} 
            for msg in conversation_history[:-1]  # Exclude the last message (current user message)
        ]
        
        # Get response using Chain-of-Thought prompting
        response = self.ollama_client.chat_with_system_prompt(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=user_message,
            conversation_history=llm_history,
            temperature=0.7
        )
        
        return response
    
    def generate_specification(self, conversation_history: List[Dict[str, str]]) -> str:
        """
        Generate IEEE-830 specification from conversation history
        
        Args:
            conversation_history: Complete conversation history
        
        Returns:
            Formatted SRS document as string
        """
        # Prepare conversation summary for specification generation
        conversation_text = self._format_conversation_for_spec(conversation_history)
        
        # Create prompt for specification generation
        spec_prompt = f"{self.SPECIFICATION_GENERATION_PROMPT}\n\n## CONVERSATION HISTORY:\n\n{conversation_text}\n\nNow generate the complete SRS document:"
        
        # Generate specification
        specification = self.ollama_client.chat_with_system_prompt(
            system_prompt="You are a technical writer specializing in software requirements specifications.",
            user_message=spec_prompt,
            temperature=0.3  # Lower temperature for more consistent output
        )
        
        return specification
    
    def _format_conversation_for_spec(self, conversation_history: List[Dict[str, str]]) -> str:
        """
        Format conversation history for specification generation
        
        Args:
            conversation_history: List of conversation messages
        
        Returns:
            Formatted conversation text
        """
        formatted = []
        
        for msg in conversation_history:
            role = msg['role'].upper()
            content = msg['content']
            formatted.append(f"{role}: {content}")
        
        return "\n\n".join(formatted)
    
    def detect_ambiguity(self, text: str) -> List[str]:
        """
        Detect ambiguous terms in requirements text
        Based on research from papers [29][31]
        
        Args:
            text: Text to analyze
        
        Returns:
            List of detected ambiguous phrases
        """
        # Vague words from paper [29]
        vague_words = [
            'fast', 'slow', 'quick', 'efficient', 'user-friendly', 
            'easy', 'simple', 'reliable', 'robust', 'scalable',
            'flexible', 'intuitive', 'appropriate', 'adequate',
            'reasonable', 'normal', 'usual', 'typical'
        ]
        
        # Weak phrases from paper [29]
        weak_phrases = [
            'if possible', 'as appropriate', 'as needed', 'if required',
            'when necessary', 'to the extent possible', 'where applicable'
        ]
        
        text_lower = text.lower()
        detected = []
        
        for word in vague_words:
            if word in text_lower:
                detected.append(f"Vague term: '{word}'")
        
        for phrase in weak_phrases:
            if phrase in text_lower:
                detected.append(f"Weak phrase: '{phrase}'")
        
        return detected
    
    def apply_4w_analysis(self, requirement: str) -> Dict[str, str]:
        """
        Apply 4W analysis (Who, What, When, Where) to a requirement
        Based on paper [31]
        
        Args:
            requirement: Requirement text to analyze
        
        Returns:
            Dictionary with 4W analysis questions
        """
        questions = {
            'who': f"WHO: Who will use this feature or be affected by '{requirement}'?",
            'what': f"WHAT: What specific actions or data are involved in '{requirement}'?",
            'when': f"WHEN: When should '{requirement}' occur or be available?",
            'where': f"WHERE: Where in the system will '{requirement}' be implemented?"
        }
        
        return questions