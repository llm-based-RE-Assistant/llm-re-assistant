from src.utils.ollama_client import OllamaClient


class SuggestionAgent:
    """
    Uses an LLM to generate actionable improvement suggestions
    based on detected validation issues.
    Falls back to rule-based suggestions if LLM is unavailable.
    """

    def __init__(self):
        self.llm = OllamaClient()
        self._llm_available = None  # Cache connection status

    def _check_llm_availability(self) -> bool:
        """Check if LLM is available (cached)"""
        if self._llm_available is None:
            self._llm_available = self.llm.check_connection()
        return self._llm_available

    def _generate_rule_based_suggestions(self, issues: list) -> list:
        """
        Generate suggestions based on detected issues using rules.
        Fallback when LLM is unavailable.
        """
        suggestions = []
        
        for issue in issues:
            issue_type = issue.get('type')
            
            if issue_type == 'vague_term':
                term = issue.get('term', '')
                suggestions.append(
                    f"Replace the vague term '{term}' with a specific, measurable criterion "
                    f"(e.g., 'response time < 2 seconds' instead of 'fast')"
                )
            
            elif issue_type == 'weak_phrase':
                phrase = issue.get('phrase', '')
                suggestions.append(
                    f"Remove the optional language '{phrase}' and make the requirement mandatory. "
                    f"Use 'shall' instead of 'should' or 'may'."
                )
            
            elif issue_type == 'missing_actor':
                suggestions.append(
                    "Specify who performs the action. Add an actor such as 'The user shall...', "
                    "'The system shall...', or 'The administrator shall...'"
                )
            
            elif issue_type == 'missing_condition':
                suggestions.append(
                    "Add a temporal constraint to specify when this requirement applies "
                    "(e.g., 'within 5 seconds', 'before user logout', 'during business hours')"
                )
            
            elif issue_type == 'contradiction':
                details = issue.get('details', '')
                suggestions.append(
                    f"Resolve the logical contradiction: {details}. "
                    f"Requirements must be internally consistent."
                )
        
        # Remove duplicates while preserving order
        seen = set()
        unique_suggestions = []
        for suggestion in suggestions:
            if suggestion not in seen:
                seen.add(suggestion)
                unique_suggestions.append(suggestion)
        
        return unique_suggestions

    def generate_suggestions(self, requirement_text: str, issues: list) -> list:
        """
        Generate actionable improvement suggestions.
        Tries LLM first, falls back to rule-based if unavailable.
        
        Args:
            requirement_text: The requirement text
            issues: List of detected issues
            
        Returns:
            List of suggestion strings
        """
        if not issues:
            return []

        # Try LLM if available
        if self._check_llm_availability():
            try:
                suggestions = self._generate_llm_suggestions(requirement_text, issues)
                
                # Check if LLM actually worked
                if suggestions and not any(
                    "trouble connecting" in s.lower() or "unexpected error" in s.lower()
                    for s in suggestions
                ):
                    return suggestions
            except Exception as e:
                print(f"LLM suggestion generation failed: {e}")
        
        # Fallback to rule-based suggestions
        print("Using rule-based suggestion fallback")
        return self._generate_rule_based_suggestions(issues)

    def _generate_llm_suggestions(self, requirement_text: str, issues: list) -> list:
        """
        Generate suggestions using LLM.
        
        Args:
            requirement_text: The requirement text
            issues: List of detected issues
            
        Returns:
            List of suggestion strings
        """
        issues_text = "\n".join(
            f"- {issue.get('type')}: {issue.get('details', issue.get('term', issue.get('phrase', '')))}"
            for issue in issues
        )

        system_prompt = (
            "You are a senior requirements engineer specializing in writing clear, "
            "unambiguous, and testable requirements according to IEEE 830 standards."
        )
        
        user_message = f"""
Requirement:
"{requirement_text}"

Detected problems:
{issues_text}

Task:
Provide 2-4 clear, actionable suggestions to improve this requirement.
Each suggestion should be:
- Specific and concrete
- Measurable or verifiable
- Directly addressing one of the detected problems

Format: Return ONLY a bullet-point list with one suggestion per line, starting with "- ".
"""

        response = self.llm.chat_with_system_prompt(
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=0.7
        )

        # Parse LLM response into list
        suggestions = []
        for line in response.split("\n"):
            line = line.strip()
            if line and (line.startswith("-") or line.startswith("•") or line.startswith("*")):
                # Remove bullet point markers
                suggestion = line.lstrip("-•* ").strip()
                if suggestion:
                    suggestions.append(suggestion)
        
        return suggestions if suggestions else self._generate_rule_based_suggestions(issues)