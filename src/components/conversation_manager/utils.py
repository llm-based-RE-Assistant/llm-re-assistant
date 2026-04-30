from dataclasses import dataclass, field

# ── Duplicate detection helper ──

def _message_similarity(a: str, b: str) -> float:
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)

# ── SMART Quality Check ──

SMART_CHECK_PROMPT = """\
You are an expert Requirements Engineer performing a SMART quality check.

CUSTOMER MESSAGE (context):
{user_message}

EXTRACTED REQUIREMENTS:
{requirements_list}

For EACH requirement, evaluate SMART criteria (Specific, Measurable, Testable, Unambiguous, Relevant).
- If it passes all 5, keep as-is.
- If it fails Measurable or Specific, REWRITE to add concrete numbers or remove vague terms.

Return a JSON array with one object per requirement:
{{
  "original": "<original text>",
  "final": "<rewritten or same>",
  "smart_score": <1-5>,
  "specific": true/false,
  "measurable": true/false,
  "testable": true/false,
  "unambiguous": true/false,
  "relevant": true/false,
  "rewritten": true/false
}}
Return ONLY the JSON array. No markdown, no explanation."""

# -- Phase transition trigger message (hidden from SRS enricher) --
TRANSITION_MSG = "__SYSTEM_TRANSITION__"

# trigger message per transition type
TRIGGER_MESSAGES = {
    ("scope", "fr"):
        "The project scope is now confirmed. "
        "Please begin requirements elicitation for the first feature.",
    ("fr", "nfr"):
        "All functional domains have been covered. "
        "Please begin the non-functional requirements phase.",
    ("nfr", "ieee"):
        "All non-functional requirement categories are satisfied. "
        "Please begin the IEEE-830 documentation sections phase.",
}
 
# ---------------------------------------------------------------------------
# SendTurnResult - returned by send_turn() instead of a plain string
# ---------------------------------------------------------------------------
 
@dataclass
class SendTurnResult:
    """Result of a single send_turn() call.
 
    primary_response   - the main assistant reply (always present).
    follow_up_message - zero or more additional assistant messages generated
                         automatically on a phase transition (scope->FR, FR->NFR,
                         NFR->IEEE). The UI renders these as separate chat bubbles,
                         giving the user a seamless transition with no dead turn.
    phase_transitioned - True when a phase boundary was crossed this turn.
    new_phase          - the phase entered after the transition, if any.
    """
    primary_response:   str
    follow_up_message: str = ""
    phase_transitioned: bool  = False
    new_phase:          str   = ""


SYSTEM_PROMPT_TRANS_1 = """\
    You are a helpful and precise assistant for requirements engineering. 
    The elicitation phase has just transitioned from {from_phase} to {to_phase}. 
    Please ask a question about the feature {domain} to elicit requirements.
    Ask user to describe a specific use scenario for this feature, including the actors involved, their goals, and the context in which they would use the feature. 
    Open by describing the most likely use scenario for this feature and ask the customer to confirm,
    correct, or extend it. This grounds the conversation immediately in concrete
    behaviour rather than leaving it open-ended.
    Example : "I imagine [actor] would [do X] when [situation] — is that right,
    and is there anything they'd need to do before or after that step?"
    Note: Return ONLY the Question. No preamble, no explanation.
"""

SYSTEM_PROMPT_TRANS_2 = """\
    You are a helpful and precise assistant for requirements engineering.
    The elicitation phase has just transitioned from {from_phase} to {to_phase}.
    Now that we are in the non-functional requirements phase, please review the functional requirements extracted so
    far and identify any non-functional aspects that are missing or could be clarified.
    For each functional requirement, consider: what could go wrong with this feature? What are the performance,
    usability, security, reliability, compatibility, or maintainability considerations? Are there any constraints or
    assumptions that should be captured? This will help ensure we have a comprehensive set of NFRs to work with in the next phase.
    Example pattern: "For the functional requirement '[requirement]', one non-functional aspect to consider is [aspect], because [reason]. A possible non-functional requirement to capture this would be: '[NFR]'."
    Note: Return ONLY the Question. No preamble, no explanation.
"""

SYSTEM_PROMPT_TRANS_3 = """\
    You are a helpful and precise assistant for requirements engineering.
    The elicitation phase has just transitioned from {from_phase} to {to_phase}.
    Now that we are in the IEEE phase, please review the requirements extracted so far and identify any that are vague, ambiguous, or incomplete.
    For each such requirement, rewrite it to be more specific and actionable, and explain what was
    vague about the original. This will help ensure the requirements are in good shape for the final SRS generation.
    Example pattern: "The requirement '[original]' is a bit vague because [reason]. A clearer way to express this would be: '[rewritten]'."
    Note: Return ONLY the Question. No preamble, no explanation.
"""