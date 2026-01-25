"""
PlantUML Syntax Validator
Validates basic PlantUML syntax for class diagrams
"""

import re
from typing import Dict, List, Tuple


class PlantUMLValidator:
    """Validates PlantUML syntax and structure"""
    
    def __init__(self):
        """Initialize validator"""
        pass
    
    def validate(self, plantuml_code: str) -> Dict[str, any]:
        """
        Validate PlantUML code syntax
        
        Args:
            plantuml_code: PlantUML code string to validate
        
        Returns:
            Dictionary with validation results:
            {
                'is_valid': bool,
                'errors': List[str],
                'warnings': List[str],
                'entities_count': int,
                'relationships_count': int
            }
        """
        errors = []
        warnings = []
        
        # Check for @startuml and @enduml tags
        has_start = '@startuml' in plantuml_code.lower()
        has_end = '@enduml' in plantuml_code.lower()
        
        if not has_start:
            errors.append("Missing @startuml tag")
        if not has_end:
            errors.append("Missing @enduml tag")
        
        if has_start and has_end:
            # Extract content between tags
            pattern = r'@startuml\s*(.*?)\s*@enduml'
            match = re.search(pattern, plantuml_code, re.DOTALL | re.IGNORECASE)
            
            if match:
                content = match.group(1)
                
                # Check for balanced braces
                brace_balance = self._check_balanced_braces(content)
                if brace_balance != 0:
                    errors.append(f"Unbalanced braces (difference: {brace_balance})")
                
                # Count entities and relationships
                entities_count = self._count_entities(content)
                relationships_count = self._count_relationships(content)
                
                # Check for common syntax issues
                syntax_warnings = self._check_syntax_issues(content)
                warnings.extend(syntax_warnings)
                
                return {
                    'is_valid': len(errors) == 0,
                    'errors': errors,
                    'warnings': warnings,
                    'entities_count': entities_count,
                    'relationships_count': relationships_count
                }
            else:
                errors.append("Could not extract content between @startuml and @enduml")
        
        return {
            'is_valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'entities_count': 0,
            'relationships_count': 0
        }
    
    def _check_balanced_braces(self, content: str) -> int:
        """
        Check if braces are balanced
        
        Args:
            content: Content to check
        
        Returns:
            Difference between opening and closing braces (0 = balanced)
        """
        open_braces = content.count('{')
        close_braces = content.count('}')
        return open_braces - close_braces
    
    def _count_entities(self, content: str) -> int:
        """
        Count class/entity definitions in PlantUML code
        
        Args:
            content: PlantUML content
        
        Returns:
            Number of entities found
        """
        # Match class definitions: class ClassName { ... }
        class_pattern = r'\bclass\s+\w+'
        matches = re.findall(class_pattern, content, re.IGNORECASE)
        return len(matches)
    
    def _count_relationships(self, content: str) -> int:
        """
        Count relationships in PlantUML code
        
        Args:
            content: PlantUML content
        
        Returns:
            Number of relationships found
        """
        # Match relationship patterns: Class1 -- Class2, Class1 --> Class2, etc.
        relationship_pattern = r'\w+\s*[-<>|]+.*?[-<>|]+\s*\w+'
        matches = re.findall(relationship_pattern, content)
        return len(matches)
    
    def _check_syntax_issues(self, content: str) -> List[str]:
        """
        Check for common syntax issues
        
        Args:
            content: PlantUML content
        
        Returns:
            List of warning messages
        """
        warnings = []
        
        # Check for classes without attributes or methods
        class_pattern = r'class\s+(\w+)\s*\{[^}]*\}'
        classes = re.finditer(class_pattern, content, re.IGNORECASE | re.DOTALL)
        
        for match in classes:
            class_name = match.group(1)
            class_body = match.group(0)
            # Check if class body is empty or only whitespace
            body_content = class_body[class_body.find('{')+1:class_body.rfind('}')].strip()
            if not body_content:
                warnings.append(f"Class '{class_name}' has no attributes or methods")
        
        # Check for relationships without multiplicities (warning, not error)
        relationship_pattern = r'(\w+)\s*[-<>|]+\s*(\w+)'
        relationships = re.finditer(relationship_pattern, content)
        
        for match in relationships:
            rel_line = match.group(0)
            # Check if relationship has multiplicity notation
            if not re.search(r'["\d]+\s*[-<>|]', rel_line):
                # This is just a warning, not all relationships need multiplicities
                pass
        
        return warnings
    
    def extract_entities(self, plantuml_code: str) -> List[str]:
        """
        Extract entity/class names from PlantUML code
        
        Args:
            plantuml_code: PlantUML code string
        
        Returns:
            List of entity names
        """
        entities = []
        
        # Extract class names
        class_pattern = r'\bclass\s+(\w+)'
        matches = re.findall(class_pattern, plantuml_code, re.IGNORECASE)
        entities.extend(matches)
        
        return list(set(entities))  # Remove duplicates

