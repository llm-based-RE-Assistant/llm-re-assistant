"""
Conversation Manager - Handles session management and conversation history
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Optional
import uuid


class ConversationManager:
    """Manages conversation sessions and history"""
    
    def __init__(self, artifacts_dir: str = 'artifacts/conversations'):
        """
        Initialize conversation manager
        
        Args:
            artifacts_dir: Directory to store conversation artifacts
        """
        self.artifacts_dir = artifacts_dir
        self.sessions = {}
        os.makedirs(artifacts_dir, exist_ok=True)
    
    def create_session(self) -> str:
        """
        Create a new conversation session
        
        Returns:
            Session ID (UUID string)
        """
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            'id': session_id,
            'created_at': datetime.now().isoformat(),
            'messages': [],
            'metadata': {
                'project_name': None,
                'project_description': None,
                'elicited_requirements': []
            }
        }
        return session_id
    
    def add_message(self, session_id: str, role: str, content: str) -> None:
        """
        Add a message to conversation history
        
        Args:
            session_id: Session identifier
            role: Message role ('user' or 'assistant')
            content: Message content
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        message = {
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat()
        }
        
        self.sessions[session_id]['messages'].append(message)
    
    def get_conversation(self, session_id: str) -> List[Dict[str, str]]:
        """
        Get conversation history for a session
        
        Args:
            session_id: Session identifier
        
        Returns:
            List of message dictionaries
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        return self.sessions[session_id]['messages']
    
    def get_conversation_text_only(self, session_id: str) -> List[Dict[str, str]]:
        """
        Get conversation history without timestamps (for LLM input)
        
        Args:
            session_id: Session identifier
        
        Returns:
            List of dicts with 'role' and 'content' only
        """
        messages = self.get_conversation(session_id)
        return [{'role': msg['role'], 'content': msg['content']} for msg in messages]
    
    def update_metadata(self, session_id: str, key: str, value: any) -> None:
        """
        Update session metadata
        
        Args:
            session_id: Session identifier
            key: Metadata key
            value: Metadata value
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        self.sessions[session_id]['metadata'][key] = value
    
    def add_requirement(self, session_id: str, requirement: Dict) -> None:
        """
        Add an elicited requirement to session metadata
        
        Args:
            session_id: Session identifier
            requirement: Requirement dictionary
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        self.sessions[session_id]['metadata']['elicited_requirements'].append(requirement)
    
    def save_conversation(self, session_id: str) -> str:
        """
        Save conversation to disk
        
        Args:
            session_id: Session identifier
        
        Returns:
            Path to saved file
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        filename = os.path.join(self.artifacts_dir, f'conversation_{session_id}.json')
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.sessions[session_id], f, indent=2, ensure_ascii=False)
        
        return filename
    
    def load_conversation(self, session_id: str) -> bool:
        """
        Load conversation from disk
        
        Args:
            session_id: Session identifier
        
        Returns:
            True if successful, False otherwise
        """
        filename = os.path.join(self.artifacts_dir, f'conversation_{session_id}.json')
        
        if not os.path.exists(filename):
            return False
        
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                self.sessions[session_id] = json.load(f)
            return True
        except Exception as e:
            print(f"Error loading conversation: {str(e)}")
            return False
    
    def get_session_summary(self, session_id: str) -> Dict:
        """
        Get a summary of the session
        
        Args:
            session_id: Session identifier
        
        Returns:
            Dictionary with session summary
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        session = self.sessions[session_id]
        
        return {
            'session_id': session_id,
            'created_at': session['created_at'],
            'message_count': len(session['messages']),
            'project_name': session['metadata'].get('project_name'),
            'requirements_count': len(session['metadata']['elicited_requirements'])
        }