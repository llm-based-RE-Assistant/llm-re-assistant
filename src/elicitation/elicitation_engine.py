"""
Elicitation Engine - Core logic for requirements elicitation
Implements Chain-of-Thought prompting and adaptive questioning
NOW WITH: Ontology-guided requirement discovery (Paper [31])
"""

from typing import List, Dict, Optional
from src.utils.ollama_client import OllamaClient
from src.elicitation.ontology_engine import OntologyEngine


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

    def __init__(self, ollama_client: OllamaClient, enable_ontology: bool = True):
        """
        Initialize elicitation engine
        
        Args:
            ollama_client: Initialized Ollama client for LLM communication
            enable_ontology: Enable ontology-guided requirement discovery (default: True)
        """
        self.ollama_client = ollama_client
        self.enable_ontology = enable_ontology
        
        # Initialize ontology engine if enabled
        if self.enable_ontology:
            try:
                self.ontology_engine = OntologyEngine()
                print("✓ Ontology-guided discovery enabled")
            except Exception as e:
                print(f"⚠ Warning: Could not initialize ontology engine: {e}")
                self.enable_ontology = False
                self.ontology_engine = None
        else:
            self.ontology_engine = None
        
        # Store extracted requirements for later analysis
        self.extracted_requirements = []
    
    def process_message(
        self, 
        user_message: str, 
        conversation_history: List[Dict[str, str]],
        auto_discover: bool = True
    ) -> str:
        """
        Process user message and generate appropriate response
        
        Args:
            user_message: Current message from user
            conversation_history: Previous conversation messages
            auto_discover: Automatically run ontology discovery on detected requirements
        
        Returns:
            Assistant's response with optional discovery questions
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
        
        # Check if message contains a requirement and run ontology discovery
        if self.enable_ontology and auto_discover:
            discovery_insights = self._analyze_for_requirements(user_message)
            
            if discovery_insights:
                # Add discovery questions to response
                response = self._append_discovery_questions(response, discovery_insights)
        
        return response
    
    def _analyze_for_requirements(self, message: str) -> Optional[Dict]:
        """
        Analyze user message for potential requirements and run ontology discovery.
        
        Args:
            message: User's message
            
        Returns:
            Discovery insights dictionary or None
        """
        # Check if message likely contains a requirement
        requirement_indicators = [
            'can', 'should', 'must', 'shall', 'will', 'need', 'want',
            'able to', 'allow', 'enable', 'support', 'provide', 'require'
        ]
        
        message_lower = message.lower()
        is_requirement = any(indicator in message_lower for indicator in requirement_indicators)
        
        if not is_requirement:
            return None
        
        # Run 4W analysis
        analysis = self.ontology_engine.analyze_4w(message)
        
        # Only return if there are missing elements
        if analysis['missing_count'] > 0:
            # Store requirement for later comprehensive analysis
            self.extracted_requirements.append({
                'id': f"REQ_{len(self.extracted_requirements) + 1:03d}",
                'text': message,
                'timestamp': None  # Could add timestamp if needed
            })
            
            return {
                'missing_count': analysis['missing_count'],
                'questions': analysis['suggestions'],
                'analysis': analysis
            }
        
        return None
    
    def _append_discovery_questions(self, response: str, insights: Dict) -> str:
        """
        Append ontology discovery questions to the response.
        
        Args:
            response: Original LLM response
            insights: Discovery insights from ontology analysis
            
        Returns:
            Enhanced response with discovery questions
        """
        if not insights or not insights['questions']:
            return response
        
        # Add a natural transition
        enhanced_response = response + "\n\n"
        enhanced_response += "**💡 Ontology Analysis - Missing Details Detected:**\n\n"
        enhanced_response += f"I've captured that requirement, but I noticed **{insights['missing_count']} element(s)** might need clarification:\n\n"
        
        for i, question in enumerate(insights['questions'], 1):
            enhanced_response += f"{i}. {question}\n"
        
        enhanced_response += "\nCould you provide more details on these aspects?"
        
        return enhanced_response
    
    def generate_comprehensive_discovery_report(self) -> Optional[Dict]:
        """
        Generate comprehensive discovery report for all collected requirements.
        
        Should be called after elicitation session is complete.
        
        Returns:
            Complete discovery report or None if ontology disabled
        """
        if not self.enable_ontology or not self.extracted_requirements:
            return None
        
        report = self.ontology_engine.generate_discovery_report(self.extracted_requirements)
        
        return report
    
    def get_discovery_summary(self) -> str:
        """
        Get human-readable summary of discovered requirements.
        
        Returns:
            Formatted text summary
        """
        if not self.enable_ontology or not self.extracted_requirements:
            return "Ontology discovery not available or no requirements collected."
        
        report = self.generate_comprehensive_discovery_report()
        
        if not report:
            return "No discovery report available."
        
        summary = "# 📊 REQUIREMENT DISCOVERY SUMMARY\n\n"
        summary += f"**Original Requirements Captured:** {report['summary']['original_requirements_count']}\n"
        summary += f"**Missing Requirements Discovered:** {report['summary']['discovered_requirements_count']}\n"
        summary += f"**Completeness Improvement:** {report['summary']['improvement_percentage']}%\n"
        summary += f"**Benchmark:** {report['summary']['benchmark_comparison']}\n\n"
        
        summary += "## Discovery Breakdown:\n"
        summary += f"- 4W Analysis Discoveries: {report['categories']['4w_analysis']}\n"
        summary += f"- Complementary Operations Missing: {report['categories']['complementary']}\n"
        summary += f"- CRUD Gaps Identified: {report['categories']['crud_missing']}\n\n"
        
        if report['discovered_requirements']:
            summary += "## 🔍 Detailed Findings:\n\n"
            
            for i, discovery in enumerate(report['discovered_requirements'][:10], 1):  # Show first 10
                summary += f"### {i}. {discovery['type'].upper().replace('_', ' ')}\n"
                
                if 'question' in discovery and discovery['question']:
                    summary += f"   **Question:** {discovery['question']}\n"
                
                if 'suggestion' in discovery and discovery['suggestion']:
                    summary += f"   **Suggestion:** {discovery['suggestion']}\n"
                
                if 'original_req_id' in discovery:
                    summary += f"   **Related to:** {discovery['original_req_id']}\n"
                
                summary += f"   **Priority:** {discovery.get('priority', 'medium')}\n\n"
            
            if len(report['discovered_requirements']) > 10:
                summary += f"... and {len(report['discovered_requirements']) - 10} more discoveries\n\n"
        
        # CRUD Completeness Summary
        if report['crud_completeness']:
            summary += "## 📋 CRUD Completeness Report:\n\n"
            
            for entity, status in list(report['crud_completeness'].items())[:5]:  # Show first 5
                summary += f"### {entity}\n"
                summary += f"   **Completeness:** {status['completeness_percentage']:.1f}%\n"
                summary += f"   **Present:** {', '.join(status['present_operations']) if status['present_operations'] else 'None'}\n"
                summary += f"   **Missing:** {', '.join(status['missing_operations']) if status['missing_operations'] else 'None'}\n\n"
        
        return summary
    
    def check_complementary_operations(self) -> List[Dict]:
        """
        Check for missing complementary operations in collected requirements.
        
        Returns:
            List of missing complementary operations
        """
        if not self.enable_ontology or not self.extracted_requirements:
            return []
        
        return self.ontology_engine.check_complementary(self.extracted_requirements)
    
    def check_crud_completeness(self) -> Dict:
        """
        Check CRUD completeness for entities in collected requirements.
        
        Returns:
            Dictionary mapping entities to CRUD status
        """
        if not self.enable_ontology or not self.extracted_requirements:
            return {}
        
        return self.ontology_engine.check_crud_completeness(self.extracted_requirements)
    
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
        
        # Append discovery report if ontology is enabled
        if self.enable_ontology and self.extracted_requirements:
            discovery_summary = self.get_discovery_summary()
            specification += f"\n\n---\n\n{discovery_summary}"
        
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
        # Use ontology engine if available
        if self.enable_ontology:
            analysis = self.ontology_engine.analyze_4w(requirement)
            
            # Convert to old format for backward compatibility
            questions = {
                'who': analysis['who']['question'] if not analysis['who']['present'] else f"WHO: {analysis['who']['value']}",
                'what': analysis['what']['question'] if not analysis['what']['present'] else f"WHAT: {analysis['what']['value']}",
                'when': analysis['when']['question'] if not analysis['when']['present'] else f"WHEN: {analysis['when']['value']}",
                'where': analysis['where']['question'] if not analysis['where']['present'] else f"WHERE: {analysis['where']['value']}"
            }
            return questions
        else:
            # Fallback to simple question generation
            questions = {
                'who': f"WHO: Who will use this feature or be affected by '{requirement}'?",
                'what': f"WHAT: What specific actions or data are involved in '{requirement}'?",
                'when': f"WHEN: When should '{requirement}' occur or be available?",
                'where': f"WHERE: Where in the system will '{requirement}' be implemented?"
            }
            return questions
    
    def reset_requirements(self):
        """Reset the collected requirements list."""
        self.extracted_requirements = []
    
    def get_requirements_count(self) -> int:
        """Get the number of requirements collected so far."""
        return len(self.extracted_requirements)
    
    def export_requirements(self) -> List[Dict]:
        """
        Export all collected requirements.
        
        Returns:
            List of requirement dictionaries
        """
        return self.extracted_requirements.copy()