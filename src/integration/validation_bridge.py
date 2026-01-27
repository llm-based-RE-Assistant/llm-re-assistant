"""
Validation Bridge - Connects Elicitation Engine with Validation Agent
Extracts requirements from conversations and validates their quality
"""

from typing import List, Dict, Optional
from src.agents.validation_agent import ValidationAgent
from src.utils.conversation_manager import ConversationManager
from datetime import datetime
import re


class ValidationBridge:
    """
    Bridges the chatbot elicitation system with the validation system.
    Extracts requirements from conversations and validates their quality.
    """
    
    def __init__(self, validation_agent: ValidationAgent, conversation_manager: ConversationManager):
        """
        Initialize validation bridge
        
        Args:
            validation_agent: Initialized ValidationAgent
            conversation_manager: Initialized ConversationManager
        """
        self.validator = validation_agent
        self.conversations = conversation_manager
    
    def extract_requirements_from_conversation(self, session_id: str) -> List[Dict]:
        """
        Extract requirements from conversation history using keyword matching.
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of requirement artifacts
        """
        messages = self.conversations.get_conversation(session_id)
        requirements = []
        req_counter = 1
        
        # Keywords that indicate a requirement statement
        requirement_indicators = [
            'shall', 'must', 'should', 'will',
            'need to', 'needs to', 'required to',
            'has to', 'have to', 'want to',
            'system', 'user', 'application'
        ]
        
        for msg in messages:
            # Only check user messages (requirements come from stakeholder)
            if msg['role'] == 'user':
                content = msg['content']
                
                # Check if message contains requirement indicators
                if any(indicator in content.lower() for indicator in requirement_indicators):
                    # Split into sentences
                    sentences = self._split_into_sentences(content)
                    
                    for sentence in sentences:
                        # Check if sentence looks like a requirement
                        if self._is_requirement_sentence(sentence):
                            requirement = {
                                'artifact_id': f'REQ_{session_id[:8]}_{req_counter:03d}',
                                'text': sentence.strip(),
                                'source': 'keyword_extraction',
                                'timestamp': msg.get('timestamp', ''),
                                'message_index': messages.index(msg)
                            }
                            requirements.append(requirement)
                            req_counter += 1
        
        return requirements
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences.
        
        Args:
            text: Text to split
            
        Returns:
            List of sentences
        """
        sentences = re.split(r'[.!?]+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _is_requirement_sentence(self, sentence: str) -> bool:
        """
        Check if a sentence looks like a requirement.
        
        Args:
            sentence: Sentence to check
            
        Returns:
            True if looks like a requirement
        """
        sentence_lower = sentence.lower()
        
        # Must have reasonable length
        if len(sentence.split()) < 4:
            return False
        
        # Should contain requirement keywords
        requirement_keywords = [
            'shall', 'must', 'should', 'will', 'need',
            'system', 'user', 'application', 'feature'
        ]
        
        return any(keyword in sentence_lower for keyword in requirement_keywords)
    
    def validate_conversation(self, session_id: str, add_traceability: bool = True) -> Dict:
        """
        Extract and validate all requirements from a conversation.
        
        Args:
            session_id: Session identifier
            add_traceability: Add traceability metadata to requirements
            
        Returns:
            Validation results dictionary
        """
        # Extract requirements
        requirements = self.extract_requirements_from_conversation(session_id)
        
        if not requirements:
            return {
                'status': 'no_requirements',
                'message': 'No requirements detected in conversation',
                'requirements_found': 0,
                'validated_requirements': []
            }
        
        # Validate all requirements
        validated = self.validator.validate_batch(requirements)
        
        # Add traceability metadata
        if add_traceability:
            validated = self.validator.add_traceability_metadata(validated, session_id)
        
        # Generate project report
        report = self.validator.generate_project_report(validated)
        
        # Save validation results to conversation metadata
        self._save_validation_to_conversation(session_id, validated, report)
        
        return {
            'status': 'success',
            'requirements_found': len(requirements),
            'validated_requirements': validated,
            'report': report,
            'extraction_method': 'keyword'
        }
    
    def _save_validation_to_conversation(
        self, 
        session_id: str, 
        validated_requirements: List[Dict],
        report: Dict
    ) -> None:
        """
        Save validation results to conversation metadata.
        
        Args:
            session_id: Session identifier
            validated_requirements: List of validated requirement artifacts
            report: Project validation report
        """
        self.conversations.update_metadata(
            session_id, 
            'validation_results', 
            {
                'validated_requirements': validated_requirements,
                'validation_report': report,
                'validated_at': validated_requirements[0]['validation']['validated_at'] if validated_requirements else None
            }
        )
        
        self.conversations.save_conversation(session_id)
    
    def get_validation_summary(self, session_id: str) -> Optional[Dict]:
        """
        Get validation summary for a session if it exists.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Validation summary or None
        """
        if session_id not in self.conversations.sessions:
            return None
        
        validation_data = self.conversations.sessions[session_id]['metadata'].get('validation_results')
        
        if not validation_data:
            return None
        
        report = validation_data.get('validation_report', {})
        
        return {
            'average_confidence': report.get('average_confidence', 0),
            'total_requirements': report.get('total_requirements', 0),
            'tier1_count': report.get('tier1_validations', 0),
            'tier2_count': report.get('tier2_validations', 0),
            'critical_issues': report.get('critical_issues_count', 0),
            'issues_by_type': report.get('total_issues_by_type', {})
        }
    
    def get_high_quality_requirements(
        self, 
        session_id: str, 
        min_confidence: float = 0.7
    ) -> List[Dict]:
        """
        Get only high-quality requirements from validation results.
        
        Args:
            session_id: Session identifier
            min_confidence: Minimum confidence threshold
            
        Returns:
            List of high-quality validated requirements
        """
        validation_data = self.conversations.sessions[session_id]['metadata'].get('validation_results')
        
        if not validation_data:
            return []
        
        validated_reqs = validation_data.get('validated_requirements', [])
        
        high_quality = [
            req for req in validated_reqs 
            if req['validation']['confidence_score'] >= min_confidence
        ]
        
        return high_quality
    
    def format_validation_report_for_chat(self, report: Dict, validated_requirements: List[Dict]) -> str:
        """
        Format validation report as a user-friendly chat message.
        Shows individual requirements that need improvement with suggestions.
        
        Args:
            report: Validation report dictionary
            validated_requirements: List of validated requirements with details
            
        Returns:
            Formatted text for chat display
        """
        message = "## 📊 Requirements Quality Check Complete\n\n"
        
        total = report['total_requirements']
        avg_conf = report['average_confidence']
        
        # Quality assessment
        if avg_conf >= 0.85:
            quality_emoji = "✅"
            quality_text = "Excellent"
            quality_message = "Your requirements are well-defined and ready for development!"
        elif avg_conf >= 0.70:
            quality_emoji = "✓"
            quality_text = "Good"
            quality_message = "Most requirements are clear, with minor improvements suggested below."
        elif avg_conf >= 0.50:
            quality_emoji = "⚠️"
            quality_text = "Needs Improvement"
            quality_message = "Several requirements need clarification. See suggestions below."
        else:
            quality_emoji = "❌"
            quality_text = "Poor"
            quality_message = "Requirements need significant revision. See detailed suggestions below."
        
        message += f"{quality_emoji} **Overall Quality: {quality_text}** (Score: {avg_conf})\n\n"
        message += f"📝 **{total} requirements** analyzed from our conversation.\n\n"
        message += f"{quality_message}\n\n"
        
        # Find requirements that need improvement
        needs_improvement = [
            req for req in validated_requirements 
            if req['validation']['confidence_score'] < 0.8 and req['validation'].get('suggestions')
        ]
        
        if needs_improvement:
            message += "---\n\n"
            message += f"### 💡 Requirements That Need Improvement ({len(needs_improvement)})\n\n"
            
            for idx, req in enumerate(needs_improvement, 1):
                conf_score = req['validation']['confidence_score']
                req_text = req['text']
                issues = req['validation'].get('issues', [])
                suggestions = req['validation'].get('suggestions', [])
                
                if len(req_text) > 80:
                    req_text_display = req_text[:77] + "..."
                else:
                    req_text_display = req_text
                
                indicator = "⚠️" if conf_score >= 0.6 else "❌"
                
                message += f"**{idx}. {indicator} Requirement** (Quality: {conf_score})\n"
                message += f"> {req_text_display}\n\n"
                
                if issues:
                    issue_types = set([issue.get('type', 'unknown') for issue in issues])
                    
                    if 'vague_term' in issue_types:
                        vague_terms = [issue.get('term') for issue in issues if issue.get('type') == 'vague_term']
                        message += f"**Issue:** Uses vague terms: {', '.join(f'*{term}*' for term in vague_terms)}\n\n"
                    elif 'contradiction' in issue_types:
                        message += f"**Issue:** Contains contradictory statements\n\n"
                    elif 'weak_phrase' in issue_types:
                        message += f"**Issue:** Contains weak or uncertain phrases\n\n"
                    elif 'missing_who' in issue_types or 'missing_what' in issue_types:
                        missing = [issue.get('type').replace('missing_', '').upper() for issue in issues if 'missing_' in issue.get('type', '')]
                        message += f"**Issue:** Missing completeness elements: {', '.join(missing)}\n\n"
                
                if suggestions:
                    best_suggestion = suggestions[0]
                    message += f"**✨ Suggested Improvement:**\n"
                    message += f"> {best_suggestion}\n\n"
                
                message += "---\n\n"
        
        else:
            message += "---\n\n"
            message += "🎉 **All requirements are clear and well-defined!**\n\n"
            message += "No improvements needed - your requirements are ready for the next step.\n\n"
        
        good_requirements = total - len(needs_improvement)
        if good_requirements > 0:
            message += f"✅ **{good_requirements} requirements** are already well-defined and need no changes.\n\n"
        
        if report.get('safety_critical_count', 0) > 0:
            message += f"🔒 **Note:** {report['safety_critical_count']} requirements involve security or critical functionality.\n\n"
        
        return message