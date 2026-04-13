
# ── Duplicate detection helper ──

def _message_similarity(a: str, b: str) -> float:
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)

# ── SMART Quality Check ──

_SMART_CHECK_PROMPT = """\
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