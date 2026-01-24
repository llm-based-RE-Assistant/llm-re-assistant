"""
Ontology Engine - Requirement Discovery System
Implements 4W analysis, complementary rules, and CRUD completeness checks
Based on Paper [31]: IEEE-830 Process with Ontology Rules
"""

import json
import re
from typing import List, Dict, Set, Tuple
from pathlib import Path
from src.elicitation.requirement_parser import RequirementParser


class OntologyEngine:
    """
    Ontology-guided requirement discovery engine.
    
    Automatically discovers missing requirements through:
    1. 4W Analysis (Who, What, When, Where)
    2. Complementary operation detection (login/logout pairs)
    3. CRUD completeness checking
    
    Based on research showing average 4.4 missing requirements discovered per project
    with 15-20% completeness improvement (Paper [31])
    """
    
    def __init__(self, config_path: str = "config/complementary_rules.json"):
        """
        Initialize ontology engine with configuration.
        
        Args:
            config_path: Path to complementary rules configuration file
        """
        self.parser = RequirementParser()
        self.complementary_pairs = self._load_complementary_rules(config_path)
        self.crud_operations = {'create', 'read', 'update', 'delete'}
        
    def _load_complementary_rules(self, config_path: str) -> Dict[str, str]:
        """
        Load complementary operation pairs from configuration.
        
        Args:
            config_path: Path to JSON configuration file
            
        Returns:
            Dictionary mapping operations to their complements
        """
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config.get('complementary_pairs', {})
        except FileNotFoundError:
            # Return default pairs if config file doesn't exist
            return {
                "login": "logout",
                "create": "delete",
                "upload": "download",
                "deposit": "withdraw",
                "add": "remove",
                "open": "close",
                "start": "stop",
                "enable": "disable",
                "lock": "unlock",
                "connect": "disconnect",
                "attach": "detach",
                "register": "unregister",
                "subscribe": "unsubscribe",
                "activate": "deactivate"
            }
    
    def analyze_4w(self, requirement: str, req_id: str = None) -> Dict[str, any]:
        """
        Analyze requirement for WHO, WHAT, WHEN, WHERE completeness.
        
        Based on Paper [31] 4W analysis framework for requirement discovery.
        
        Args:
            requirement: Requirement text to analyze
            req_id: Optional requirement ID for reference
            
        Returns:
            Dictionary containing:
            - who: {present: bool, value: str, question: str}
            - what: {present: bool, value: str, question: str}
            - when: {present: bool, value: str, question: str}
            - where: {present: bool, value: str, question: str}
            - missing_count: int
            - suggestions: List[str]
        """
        parsed = self.parser.parse_requirement(requirement)
        
        analysis = {
            'requirement_id': req_id,
            'requirement_text': requirement,
            'who': self._analyze_who(requirement, parsed),
            'what': self._analyze_what(requirement, parsed),
            'when': self._analyze_when(requirement, parsed),
            'where': self._analyze_where(requirement, parsed),
            'missing_count': 0,
            'suggestions': []
        }
        
        # Count missing elements
        for dimension in ['who', 'what', 'when', 'where']:
            if not analysis[dimension]['present']:
                analysis['missing_count'] += 1
                analysis['suggestions'].append(analysis[dimension]['question'])
        
        return analysis
    
    def _analyze_who(self, requirement: str, parsed: Dict) -> Dict[str, any]:
        """Analyze WHO dimension - actor/user role."""
        actors = parsed.get('actors', [])
        
        if actors:
            return {
                'present': True,
                'value': ', '.join(actors),
                'question': None
            }
        else:
            return {
                'present': False,
                'value': None,
                'question': f"WHO can perform this action? (user role, actor, or system component)"
            }
    
    def _analyze_what(self, requirement: str, parsed: Dict) -> Dict[str, any]:
        """Analyze WHAT dimension - action/operation."""
        actions = parsed.get('actions', [])
        entities = parsed.get('entities', [])
        
        if actions:
            return {
                'present': True,
                'value': ', '.join(actions),
                'question': None
            }
        else:
            return {
                'present': False,
                'value': None,
                'question': f"WHAT specific action or operation is performed?"
            }
    
    def _analyze_when(self, requirement: str, parsed: Dict) -> Dict[str, any]:
        """Analyze WHEN dimension - timing/conditions."""
        # Keywords indicating timing/conditions
        timing_keywords = [
            'when', 'after', 'before', 'during', 'while', 'until',
            'hours', 'time', 'daily', 'weekly', 'monthly',
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
            'morning', 'afternoon', 'evening', 'night',
            'am', 'pm', 'o\'clock'
        ]
        
        req_lower = requirement.lower()
        has_timing = any(keyword in req_lower for keyword in timing_keywords)
        
        if has_timing:
            # Extract timing information
            timing_info = [kw for kw in timing_keywords if kw in req_lower]
            return {
                'present': True,
                'value': ', '.join(timing_info),
                'question': None
            }
        else:
            return {
                'present': False,
                'value': None,
                'question': f"WHEN can this action be performed? (timing, conditions, business hours, triggers)"
            }
    
    def _analyze_where(self, requirement: str, parsed: Dict) -> Dict[str, any]:
        """Analyze WHERE dimension - location/context."""
        # Keywords indicating location/context
        location_keywords = [
            'web', 'mobile', 'app', 'application', 'interface', 'ui', 'gui',
            'backend', 'frontend', 'server', 'client', 'database',
            'api', 'endpoint', 'service', 'dashboard', 'portal',
            'screen', 'page', 'form', 'dialog', 'modal',
            'atm', 'terminal', 'kiosk', 'counter', 'branch'
        ]
        
        req_lower = requirement.lower()
        has_location = any(keyword in req_lower for keyword in location_keywords)
        
        if has_location:
            location_info = [kw for kw in location_keywords if kw in req_lower]
            return {
                'present': True,
                'value': ', '.join(location_info),
                'question': None
            }
        else:
            return {
                'present': False,
                'value': None,
                'question': f"WHERE does this action occur? (UI component, backend service, API, physical location)"
            }
    
    def check_complementary(self, requirements: List[Dict[str, str]]) -> List[Dict[str, any]]:
        """
        Check for missing complementary operations.
        
        For example, if "login" exists, checks if "logout" exists.
        
        Args:
            requirements: List of requirement dictionaries with 'id' and 'text' keys
            
        Returns:
            List of missing complementary operations with suggestions
        """
        missing_complements = []
        
        # Extract all actions from all requirements
        all_actions = set()
        action_to_req = {}  # Map action to requirement ID
        
        for req in requirements:
            req_text = req.get('text', req.get('content', ''))
            req_id = req.get('id', 'Unknown')
            
            parsed = self.parser.parse_requirement(req_text)
            actions = parsed.get('actions', [])
            
            for action in actions:
                action_lower = action.lower()
                all_actions.add(action_lower)
                action_to_req[action_lower] = req_id
        
        # Check for missing complements
        for action in all_actions:
            if action in self.complementary_pairs:
                complement = self.complementary_pairs[action]
                
                if complement not in all_actions:
                    missing_complements.append({
                        'type': 'complementary',
                        'trigger_action': action,
                        'trigger_req_id': action_to_req[action],
                        'missing_action': complement,
                        'suggestion': f"Consider adding '{complement}' functionality as complement to '{action}'",
                        'priority': 'medium'
                    })
        
        return missing_complements
    
    def check_crud_completeness(self, requirements: List[Dict[str, str]]) -> Dict[str, any]:
        """
        Check CRUD (Create, Read, Update, Delete) completeness for entities.
        
        Args:
            requirements: List of requirement dictionaries
            
        Returns:
            Dictionary mapping entities to their CRUD completeness status
        """
        entity_operations = {}  # entity -> set of CRUD operations found
        
        # Extract entities and their operations
        for req in requirements:
            req_text = req.get('text', req.get('content', ''))
            req_id = req.get('id', 'Unknown')
            
            parsed = self.parser.parse_requirement(req_text)
            entities = parsed.get('entities', [])
            actions = parsed.get('actions', [])
            
            # Map actions to CRUD operations
            crud_mapping = self._map_to_crud(actions)
            
            for entity in entities:
                if entity not in entity_operations:
                    entity_operations[entity] = {
                        'create': set(),
                        'read': set(),
                        'update': set(),
                        'delete': set()
                    }
                
                for crud_op in crud_mapping:
                    entity_operations[entity][crud_op].add(req_id)
        
        # Check completeness and generate suggestions
        completeness_report = {}
        
        for entity, operations in entity_operations.items():
            missing = []
            present = []
            
            for crud_op in ['create', 'read', 'update', 'delete']:
                if operations[crud_op]:
                    present.append(crud_op)
                else:
                    missing.append(crud_op)
            
            completeness_report[entity] = {
                'present_operations': present,
                'missing_operations': missing,
                'completeness_percentage': (len(present) / 4) * 100,
                'suggestions': self._generate_crud_suggestions(entity, missing)
            }
        
        return completeness_report
    
    def _map_to_crud(self, actions: List[str]) -> Set[str]:
        """Map action verbs to CRUD operations."""
        crud_verbs = {
            'create': ['create', 'add', 'insert', 'register', 'submit', 'post', 'upload', 'new'],
            'read': ['read', 'view', 'get', 'fetch', 'retrieve', 'display', 'show', 'list', 'see', 'check'],
            'update': ['update', 'edit', 'modify', 'change', 'revise', 'amend', 'adjust', 'alter'],
            'delete': ['delete', 'remove', 'cancel', 'drop', 'destroy', 'erase', 'clear']
        }
        
        found_operations = set()
        
        for action in actions:
            action_lower = action.lower()
            for crud_op, verbs in crud_verbs.items():
                if action_lower in verbs or any(verb in action_lower for verb in verbs):
                    found_operations.add(crud_op)
        
        return found_operations
    
    def _generate_crud_suggestions(self, entity: str, missing_operations: List[str]) -> List[str]:
        """Generate suggestions for missing CRUD operations."""
        suggestions = []
        
        suggestion_templates = {
            'create': f"Add functionality to create new {entity} records",
            'read': f"Add functionality to view/retrieve {entity} information",
            'update': f"Add functionality to modify existing {entity} records",
            'delete': f"Add functionality to remove/delete {entity} records"
        }
        
        for operation in missing_operations:
            suggestions.append(suggestion_templates.get(operation, f"Add {operation} operation for {entity}"))
        
        return suggestions
    
    def generate_discovery_report(self, requirements: List[Dict[str, str]]) -> Dict[str, any]:
        """
        Generate comprehensive requirement discovery report.
        
        Combines 4W analysis, complementary checks, and CRUD completeness.
        
        Args:
            requirements: List of requirement dictionaries
            
        Returns:
            Complete discovery report with metrics and suggestions
        """
        discovered_requirements = []
        
        # 1. Run 4W analysis on each requirement
        for req in requirements:
            req_text = req.get('text', req.get('content', ''))
            req_id = req.get('id', f"REQ_{requirements.index(req)+1:03d}")
            
            analysis = self.analyze_4w(req_text, req_id)
            
            if analysis['missing_count'] > 0:
                for dimension in ['who', 'what', 'when', 'where']:
                    if not analysis[dimension]['present']:
                        discovered_requirements.append({
                            'type': f'4w_{dimension}',
                            'original_req_id': req_id,
                            'original_req_text': req_text,
                            'question': analysis[dimension]['question'],
                            'priority': 'high' if dimension in ['who', 'what'] else 'medium'
                        })
        
        # 2. Check complementary operations
        complementary_findings = self.check_complementary(requirements)
        discovered_requirements.extend(complementary_findings)
        
        # 3. Check CRUD completeness
        crud_report = self.check_crud_completeness(requirements)
        
        for entity, status in crud_report.items():
            if status['missing_operations']:
                for suggestion in status['suggestions']:
                    discovered_requirements.append({
                        'type': 'crud_missing',
                        'entity': entity,
                        'missing_operations': status['missing_operations'],
                        'suggestion': suggestion,
                        'priority': 'medium'
                    })
        
        # Generate summary statistics
        report = {
            'summary': {
                'original_requirements_count': len(requirements),
                'discovered_requirements_count': len(discovered_requirements),
                'improvement_percentage': round((len(discovered_requirements) / len(requirements) * 100), 2) if requirements else 0,
                'benchmark_comparison': 'Paper [31] average: 4.4 discoveries per project'
            },
            'discovered_requirements': discovered_requirements,
            'crud_completeness': crud_report,
            'categories': {
                '4w_analysis': len([d for d in discovered_requirements if d['type'].startswith('4w_')]),
                'complementary': len([d for d in discovered_requirements if d['type'] == 'complementary']),
                'crud_missing': len([d for d in discovered_requirements if d['type'] == 'crud_missing'])
            }
        }
        
        return report
    
    def get_discovery_questions(self, requirement: str) -> List[str]:
        """
        Get immediate discovery questions for a single requirement.
        
        Used during real-time elicitation to ask clarifying questions.
        
        Args:
            requirement: Single requirement text
            
        Returns:
            List of clarifying questions
        """
        analysis = self.analyze_4w(requirement)
        return analysis.get('suggestions', [])