"""
Requirement Parser - NLP-based extraction of requirement components
Extracts entities, actions, and actors from requirement text
Uses spaCy for natural language processing
"""

import spacy
from typing import Dict, List, Set
import re


class RequirementParser:
    """
    Parses requirements to extract structured information.
    
    Extracts:
    - Entities: Nouns representing system objects (User, Product, Order)
    - Actions: Verbs representing operations (create, view, delete)
    - Actors: Subjects performing actions (admin, customer, system)
    """
    
    def __init__(self):
        """Initialize parser with spaCy model."""
        try:
            # Load spaCy English model
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            raise RuntimeError(
                "spaCy model 'en_core_web_sm' not found. "
                "Please install it with: python -m spacy download en_core_web_sm"
            )
        
        # Common actor/role keywords
        self.actor_keywords = {
            'user', 'admin', 'administrator', 'customer', 'client', 'guest',
            'manager', 'employee', 'staff', 'member', 'visitor', 'owner',
            'system', 'service', 'application', 'server', 'api',
            'student', 'teacher', 'instructor', 'developer', 'tester',
            'buyer', 'seller', 'vendor', 'supplier', 'patient', 'doctor'
        }
        
        # Common action verbs (expanded list)
        self.action_verbs = {
            # CRUD operations
            'create', 'add', 'insert', 'register', 'submit', 'post', 'new',
            'read', 'view', 'get', 'fetch', 'retrieve', 'display', 'show', 'list', 'see',
            'update', 'edit', 'modify', 'change', 'revise', 'amend', 'adjust',
            'delete', 'remove', 'cancel', 'drop', 'destroy', 'erase', 'clear',
            
            # Authentication & Authorization
            'login', 'logout', 'authenticate', 'authorize', 'verify', 'validate',
            'register', 'unregister', 'activate', 'deactivate',
            
            # Data operations
            'upload', 'download', 'import', 'export', 'transfer', 'send', 'receive',
            'save', 'load', 'store', 'retrieve', 'backup', 'restore',
            
            # Business operations
            'order', 'purchase', 'buy', 'sell', 'pay', 'refund', 'charge',
            'deposit', 'withdraw', 'transfer', 'process', 'approve', 'reject',
            
            # Communication
            'notify', 'alert', 'inform', 'message', 'email', 'send', 'receive',
            
            # Control operations
            'start', 'stop', 'pause', 'resume', 'enable', 'disable',
            'open', 'close', 'lock', 'unlock', 'block', 'unblock',
            
            # Search & Filter
            'search', 'filter', 'sort', 'find', 'query', 'browse',
            
            # Configuration
            'configure', 'setup', 'install', 'uninstall', 'customize', 'personalize'
        }
        
        # Entity type keywords
        self.entity_keywords = {
            'account', 'profile', 'user', 'customer', 'product', 'item', 'order',
            'transaction', 'payment', 'invoice', 'document', 'file', 'report',
            'message', 'notification', 'alert', 'email', 'data', 'record',
            'database', 'table', 'form', 'page', 'screen', 'interface',
            'service', 'api', 'endpoint', 'request', 'response', 'session'
        }
    
    def parse_requirement(self, requirement_text: str) -> Dict[str, List[str]]:
        """
        Parse requirement text to extract structured components.
        
        Args:
            requirement_text: Natural language requirement text
            
        Returns:
            Dictionary containing:
            - entities: List of identified entities (nouns)
            - actions: List of identified actions (verbs)
            - actors: List of identified actors (subjects)
        """
        # Process text with spaCy
        doc = self.nlp(requirement_text)
        
        # Extract components
        entities = self._extract_entities(doc)
        actions = self._extract_actions(doc)
        actors = self._extract_actors(doc)
        
        return {
            'entities': list(entities),
            'actions': list(actions),
            'actors': list(actors),
            'raw_text': requirement_text
        }
    
    def _extract_entities(self, doc) -> Set[str]:
        """
        Extract entities (nouns representing system objects).
        
        Args:
            doc: spaCy Doc object
            
        Returns:
            Set of entity names
        """
        entities = set()
        
        # Extract nouns and noun phrases
        for token in doc:
            # Check if token is a noun and matches entity keywords
            if token.pos_ in ['NOUN', 'PROPN']:
                lemma = token.lemma_.lower()
                
                # Add if it's a known entity keyword
                if lemma in self.entity_keywords:
                    entities.add(token.text.capitalize())
                
                # Add if it's a proper noun (likely an entity name)
                elif token.pos_ == 'PROPN':
                    entities.add(token.text)
                
                # Add compound nouns (e.g., "user account", "product catalog")
                elif token.dep_ == 'compound':
                    compound_phrase = f"{token.text} {token.head.text}"
                    entities.add(compound_phrase.title())
        
        # Extract noun chunks for multi-word entities
        for chunk in doc.noun_chunks:
            chunk_text = chunk.text.lower()
            # Only add if it contains known entity keywords
            if any(keyword in chunk_text for keyword in self.entity_keywords):
                entities.add(chunk.text.title())
        
        return entities
    
    def _extract_actions(self, doc) -> Set[str]:
        """
        Extract actions (verbs representing operations).
        
        Args:
            doc: spaCy Doc object
            
        Returns:
            Set of action verbs
        """
        actions = set()
        
        for token in doc:
            # Check if token is a verb
            if token.pos_ == 'VERB':
                lemma = token.lemma_.lower()
                
                # Add if it's a known action verb
                if lemma in self.action_verbs:
                    actions.add(lemma)
                
                # Add modal verbs' main verbs (can view, should delete)
                elif token.dep_ == 'ROOT' or token.dep_ == 'xcomp':
                    actions.add(lemma)
        
        # Also check for action keywords in text (case-insensitive)
        text_lower = doc.text.lower()
        for action in self.action_verbs:
            if re.search(r'\b' + action + r'\b', text_lower):
                actions.add(action)
        
        return actions
    
    def _extract_actors(self, doc) -> Set[str]:
        """
        Extract actors (subjects performing actions).
        
        Args:
            doc: spaCy Doc object
            
        Returns:
            Set of actor names/roles
        """
        actors = set()
        
        for token in doc:
            # Check if token is a subject
            if token.dep_ in ['nsubj', 'nsubjpass']:
                lemma = token.lemma_.lower()
                
                # Add if it's a known actor keyword
                if lemma in self.actor_keywords:
                    actors.add(token.text.capitalize())
                
                # Add proper nouns as potential actors
                elif token.pos_ == 'PROPN':
                    actors.add(token.text)
        
        # Check for actor keywords in text
        text_lower = doc.text.lower()
        for actor in self.actor_keywords:
            if re.search(r'\b' + actor + r'\b', text_lower):
                actors.add(actor.capitalize())
        
        return actors
    
    def extract_entity_names(self, requirements: List[str]) -> Set[str]:
        """
        Extract all unique entity names from a list of requirements.
        
        Useful for CRUD completeness checking.
        
        Args:
            requirements: List of requirement texts
            
        Returns:
            Set of all unique entity names
        """
        all_entities = set()
        
        for req in requirements:
            parsed = self.parse_requirement(req)
            all_entities.update(parsed['entities'])
        
        return all_entities
    
    def is_modal_verb_present(self, text: str) -> bool:
        """
        Check if requirement contains modal verbs (shall, should, must, can, may).
        
        Good requirements use clear modal verbs to indicate obligation level.
        
        Args:
            text: Requirement text
            
        Returns:
            True if modal verb is present
        """
        modal_verbs = ['shall', 'should', 'must', 'can', 'may', 'will', 'would']
        text_lower = text.lower()
        return any(modal in text_lower for modal in modal_verbs)
    
    def detect_ambiguous_pronouns(self, text: str) -> List[str]:
        """
        Detect ambiguous pronouns that should be avoided in requirements.
        
        Args:
            text: Requirement text
            
        Returns:
            List of detected ambiguous pronouns
        """
        ambiguous_pronouns = ['it', 'this', 'that', 'these', 'those', 'they', 'them']
        
        doc = self.nlp(text)
        detected = []
        
        for token in doc:
            if token.pos_ == 'PRON' and token.text.lower() in ambiguous_pronouns:
                detected.append(token.text)
        
        return detected                                                                                                                                                             