"""
Modeling Agent - Generates UML class diagrams from requirements
Uses GPT-4-turbo with few-shot prompting (DP7) for PlantUML code generation
Based on Papers [16] and [17]
"""

import json
import os
import re
from typing import Dict, List, Optional
from src.utils.openai_client import OpenAIClient
from src.utils.plantuml_validator import PlantUMLValidator


class ModelingAgent:
    """
    Generates UML class diagrams from requirements using GPT-4-turbo
    Implements few-shot prompting pattern (DP7) for structured output
    """
    
    def __init__(self, openai_client: Optional[OpenAIClient] = None):
        """
        Initialize modeling agent
        
        Args:
            openai_client: Initialized OpenAI client (creates new one if None, lazy initialization)
        """
        self._openai_client = openai_client  # Store client, but don't initialize yet
        self.validator = PlantUMLValidator()
        self.prompts = self._load_prompts()
    
    @property
    def openai_client(self) -> OpenAIClient:
        """
        Lazy initialization of OpenAI client
        Only creates client when actually needed
        """
        if self._openai_client is None:
            try:
                self._openai_client = OpenAIClient(
                    model=os.getenv('OPENAI_MODEL', 'gpt-4-turbo-preview'),
                    temperature=0.3  # Lower temperature for more consistent structured output
                )
            except ValueError as e:
                raise ValueError(
                    "OpenAI API key not provided. Set OPENAI_API_KEY environment variable. "
                    "Make sure your .env file is in the same directory as app.py and contains OPENAI_API_KEY=your-key"
                ) from e
        return self._openai_client
    
    def _load_prompts(self) -> Dict:
        """
        Load UML prompt templates from JSON file
        
        Returns:
            Dictionary with prompt templates and examples
        """
        prompts_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            'templates',
            'uml_prompts.json'
        )
        
        try:
            with open(prompts_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            # Fallback to default prompts if file not found
            return {
                "system_prompt": "You are an expert UML modeler specializing in generating PlantUML class diagrams from software requirements.",
                "few_shot_examples": [],
                "generation_instructions": "Generate PlantUML code for the following requirements."
            }
    
    def generate_uml(
        self, 
        requirements: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, any]:
        """
        Generate PlantUML code from requirements text
        
        Args:
            requirements: Requirements text or list of requirements
            conversation_history: Optional conversation history for context
        
        Returns:
            Dictionary with:
            - plantuml_code: Generated PlantUML code
            - quality: Quality assessment metrics
            - status: 'success' or 'error'
            - error: Error message if status is 'error'
        """
        try:
            # Extract requirements from conversation if needed
            if conversation_history:
                requirements_text = self._extract_requirements_from_conversation(
                    requirements, 
                    conversation_history
                )
            else:
                requirements_text = requirements
            
            # Build prompt with few-shot examples
            prompt = self._build_prompt(requirements_text)
            
            # Generate PlantUML code using GPT-4-turbo
            plantuml_code = self._generate_plantuml_code(prompt)
            
            # Clean and validate the generated code
            plantuml_code = self._clean_plantuml_code(plantuml_code)
            validation_result = self.validator.validate(plantuml_code)
            
            if not validation_result['is_valid']:
                return {
                    'status': 'error',
                    'error': f"Generated invalid PlantUML code: {', '.join(validation_result['errors'])}",
                    'plantuml_code': plantuml_code,
                    'quality': {
                        'completeness_ratio': 0.0,
                        'entities_found': 0,
                        'entities_expected': 0,
                        'warnings': validation_result['warnings'] + validation_result['errors']
                    }
                }
            
            # Assess quality
            quality = self._assess_quality(requirements_text, plantuml_code, validation_result)
            
            return {
                'status': 'success',
                'plantuml_code': plantuml_code,
                'quality': quality
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'plantuml_code': '',
                'quality': {
                    'completeness_ratio': 0.0,
                    'entities_found': 0,
                    'entities_expected': 0,
                    'warnings': [f"Generation failed: {str(e)}"]
                }
            }
    
    def _build_prompt(self, requirements: str) -> str:
        """
        Build prompt with few-shot examples (DP7: Prompt Engineering)
        
        Args:
            requirements: Requirements text
        
        Returns:
            Complete prompt string
        """
        prompt_parts = [self.prompts.get('system_prompt', '')]
        prompt_parts.append("\n\n## Few-Shot Examples:\n\n")
        
        # Add few-shot examples
        examples = self.prompts.get('few_shot_examples', [])
        for i, example in enumerate(examples[:3], 1):  # Use up to 3 examples
            prompt_parts.append(f"Example {i}:\n")
            prompt_parts.append(f"Requirements: {example['requirement']}\n")
            prompt_parts.append(f"PlantUML Code:\n{example['plantuml']}\n\n")
        
        # Add generation instructions
        prompt_parts.append("\n## Task:\n\n")
        prompt_parts.append(self.prompts.get('generation_instructions', ''))
        prompt_parts.append(f"\n\nRequirements:\n{requirements}\n\n")
        prompt_parts.append("Generate PlantUML code:")
        
        return "".join(prompt_parts)
    
    def _generate_plantuml_code(self, prompt: str) -> str:
        """
        Generate PlantUML code using GPT-4-turbo
        
        Args:
            prompt: Complete prompt with examples
        
        Returns:
            Generated PlantUML code
        """
        response = self.openai_client.chat_with_system_prompt(
            system_prompt=self.prompts.get('system_prompt', ''),
            user_message=prompt,
            temperature=0.3  # Low temperature for consistent structured output
        )
        
        return response.strip()
    
    def _clean_plantuml_code(self, code: str) -> str:
        """
        Clean and extract PlantUML code from LLM response
        Removes markdown code blocks if present
        
        Args:
            code: Raw LLM response
        
        Returns:
            Cleaned PlantUML code
        """
        # Remove markdown code blocks if present
        code = re.sub(r'```plantuml\s*\n', '', code, flags=re.IGNORECASE)
        code = re.sub(r'```uml\s*\n', '', code, flags=re.IGNORECASE)
        code = re.sub(r'```\s*\n', '', code)
        code = re.sub(r'```', '', code)
        
        # Ensure @startuml and @enduml tags are present
        if '@startuml' not in code.lower():
            code = '@startuml\n' + code
        if '@enduml' not in code.lower():
            code = code + '\n@enduml'
        
        return code.strip()
    
    def _extract_requirements_from_conversation(
        self, 
        requirements: str,
        conversation_history: List[Dict[str, str]]
    ) -> str:
        """
        Extract requirements text from conversation history
        
        Args:
            requirements: Explicit requirements text (if provided)
            conversation_history: Conversation messages
        
        Returns:
            Combined requirements text
        """
        if requirements and requirements.strip():
            return requirements
        
        # Extract user messages and assistant summaries
        req_texts = []
        for msg in conversation_history:
            if msg['role'] == 'user':
                req_texts.append(msg['content'])
            elif msg['role'] == 'assistant':
                # Extract requirement-like statements from assistant responses
                content = msg['content']
                # Look for requirement patterns
                if any(keyword in content.lower() for keyword in ['requirement', 'system', 'feature', 'function']):
                    req_texts.append(content)
        
        return "\n\n".join(req_texts) if req_texts else "No requirements found in conversation."
    
    def _assess_quality(
        self, 
        requirements: str, 
        plantuml_code: str,
        validation_result: Dict
    ) -> Dict[str, any]:
        """
        Assess quality of generated UML diagram
        Implements completeness ratio (CR) from Paper [16]
        
        Args:
            requirements: Original requirements text
            plantuml_code: Generated PlantUML code
            validation_result: Validation result from validator
        
        Returns:
            Quality assessment dictionary
        """
        # Extract entities from requirements (simple heuristic)
        expected_entities = self._extract_expected_entities(requirements)
        found_entities = self.validator.extract_entities(plantuml_code)
        
        # Calculate completeness ratio
        entities_found = len(found_entities)
        entities_expected = len(expected_entities)
        
        if entities_expected > 0:
            completeness_ratio = entities_found / entities_expected
        else:
            completeness_ratio = 1.0 if entities_found > 0 else 0.0
        
        # Check for semantic issues
        warnings = validation_result.get('warnings', []).copy()
        
        # Flag for human review if CR < 0.8
        if completeness_ratio < 0.8:
            warnings.append(f"Low completeness ratio ({completeness_ratio:.2f}). Human review recommended.")
        
        # Check for missing relationships
        relationships_count = validation_result.get('relationships_count', 0)
        if relationships_count == 0 and entities_found > 1:
            warnings.append("No relationships defined between entities. Review recommended.")
        
        # Check for orphan classes
        if entities_found > 1 and relationships_count < entities_found - 1:
            warnings.append("Some entities may be disconnected. Review relationships.")
        
        return {
            'completeness_ratio': round(completeness_ratio, 2),
            'entities_found': entities_found,
            'entities_expected': entities_expected,
            'relationships_count': relationships_count,
            'warnings': warnings,
            'found_entities': found_entities,
            'expected_entities': expected_entities
        }
    
    def _extract_expected_entities(self, requirements: str) -> List[str]:
        """
        Extract expected entity names from requirements text
        Uses simple heuristics to identify nouns that might be classes
        
        Args:
            requirements: Requirements text
        
        Returns:
            List of potential entity names
        """
        entities = []
        
        # Common patterns: "system has X", "X has Y", "track X", "manage X"
        patterns = [
            r'(?:system|application|software)\s+(?:has|manages|tracks|contains)\s+(\w+)',
            r'(\w+)\s+(?:has|contains|manages|tracks)',
            r'(?:each|every)\s+(\w+)\s+(?:has|contains)',
            r'class\s+(\w+)',
            r'entity\s+(\w+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, requirements, re.IGNORECASE)
            entities.extend(matches)
        
        # Also look for capitalized nouns (common in requirements)
        capitalized_words = re.findall(r'\b([A-Z][a-z]+)\b', requirements)
        # Filter out common words
        common_words = {'The', 'This', 'Each', 'Every', 'System', 'Application', 'Software'}
        entities.extend([w for w in capitalized_words if w not in common_words])
        
        # Remove duplicates and normalize
        entities = list(set([e.lower().capitalize() for e in entities if len(e) > 2]))
        
        return entities

