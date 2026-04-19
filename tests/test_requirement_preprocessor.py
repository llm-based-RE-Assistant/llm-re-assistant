"""
Unit tests for RequirementPreprocessor — non-LLM parts.

Tests cover:
- parse_requirements_file(): .txt parsing, .json parsing, error handling
- ProcessedRequirement.to_dict() serialization
- PreprocessResult.to_dict() serialization
- RequirementPreprocessor._fallback_batch(): passthrough behavior
- RequirementPreprocessor.process(): deduplication, domain/NFR collection
- create_preprocessor() factory
- Edge cases: empty input, unsupported file type, malformed JSON
"""

import sys
import types
import json

# Stubs — register BEFORE importing any src module.
# requirement_preprocessor.py imports:
#   from src.components.system_prompt.utils import _PREPROCESS_SYSTEM, _PREPROCESS_USER

if "src.components.system_prompt.utils" not in sys.modules:
    sys.modules["src.components.system_prompt.utils"] = types.ModuleType(
        "src.components.system_prompt.utils"
    )
_pu = sys.modules["src.components.system_prompt.utils"]
_pu._PREPROCESS_SYSTEM = "You are a requirements preprocessor."
_pu._PREPROCESS_USER   = (
    "Project: {project_context}\n"
    "Count: {count}\n"
    "Requirements:\n{req_list}"
)
_pu.PHASE4_SECTIONS = {"1.2", "2.1", "2.3"}

if "src.components.system_prompt.prompt_architect" not in sys.modules:
    sys.modules["src.components.system_prompt.prompt_architect"] = types.ModuleType(
        "src.components.system_prompt.prompt_architect"
    )
_pa = sys.modules["src.components.system_prompt.prompt_architect"]
_pa.MIN_NFR_PER_CATEGORY = 2

# Now import real classes
from src.components.requirement_preprocessor import (   # noqa: E402
    RequirementPreprocessor, ProcessedRequirement, PreprocessResult,
    parse_requirements_file, create_preprocessor,
)


# Stub LLM provider — no real API calls

class _StubProvider:
    def __init__(self, response_json=None, raise_exc=False):
        self._response = response_json
        self._raise    = raise_exc

    def chat(self, system_message, messages, temperature=0.0):
        if self._raise:
            raise RuntimeError("LLM unavailable")
        if self._response is None:
            return "[]"
        return json.dumps(self._response)


def _llm_item(original, final=None, req_type="functional",
              category="authentication", category_label="User Authentication",
              smart_score=4, was_rewritten=False, was_split=False):
    return {
        "original":       original,
        "final":          final or original,
        "req_type":       req_type,
        "category":       category,
        "category_label": category_label,
        "smart_score":    smart_score,
        "was_rewritten":  was_rewritten,
        "was_split":      was_split,
        "atomic_index":   0,
    }


# parse_requirements_file() — .txt

class TestParseRequirementsFileTxt:

    def test_parses_plain_lines(self):
        content = (
            "The system shall allow user login.\n"
            "The system shall allow user logout.\n"
        )
        reqs, err = parse_requirements_file(content, "reqs.txt")
        assert err is None
        assert len(reqs) == 2

    def test_skips_blank_lines(self):
        content = "The system shall allow login.\n\n\nThe system shall log out users.\n"
        reqs, err = parse_requirements_file(content, "reqs.txt")
        assert err is None
        assert len(reqs) == 2

    def test_skips_comment_lines(self):
        content = (
            "# This is a comment\n"
            "The system shall allow user login.\n"
            "// Another comment\n"
            "The system shall support password reset.\n"
        )
        reqs, err = parse_requirements_file(content, "reqs.txt")
        assert err is None
        assert len(reqs) == 2

    def test_strips_numbering(self):
        content = "1. The system shall allow user login.\n2. The system shall allow logout.\n"
        reqs, err = parse_requirements_file(content, "reqs.txt")
        assert err is None
        assert not reqs[0].startswith("1.")

    def test_strips_bullet_points(self):
        content = "- The system shall allow user login.\n* The system shall support MFA.\n"
        reqs, err = parse_requirements_file(content, "reqs.txt")
        assert err is None
        assert not reqs[0].startswith("-")

    def test_empty_file_returns_error(self):
        reqs, err = parse_requirements_file("", "reqs.txt")
        assert err is not None
        assert reqs == []

    def test_only_comments_returns_error(self):
        reqs, err = parse_requirements_file("# comment\n// more\n", "reqs.txt")
        assert err is not None

    def test_short_lines_filtered(self):
        content = "ok\nThe system shall authenticate users via OAuth2 protocol.\n"
        reqs, err = parse_requirements_file(content, "reqs.txt")
        assert err is None
        assert len(reqs) == 1


# parse_requirements_file() — .json

class TestParseRequirementsFileJson:

    def test_parses_string_array(self):
        data = ["The system shall allow login.", "The system shall allow logout."]
        reqs, err = parse_requirements_file(json.dumps(data), "reqs.json")
        assert err is None
        assert len(reqs) == 2

    def test_parses_object_array_text_key(self):
        data = [{"text": "The system shall allow user login via email."}]
        reqs, err = parse_requirements_file(json.dumps(data), "reqs.json")
        assert err is None
        assert len(reqs) == 1

    def test_parses_object_array_requirement_key(self):
        data = [{"requirement": "The system shall support two-factor authentication."}]
        reqs, err = parse_requirements_file(json.dumps(data), "reqs.json")
        assert err is None
        assert reqs[0] == "The system shall support two-factor authentication."

    def test_invalid_json_returns_error(self):
        reqs, err = parse_requirements_file("{invalid json", "reqs.json")
        assert err is not None
        assert reqs == []

    def test_non_array_json_returns_error(self):
        reqs, err = parse_requirements_file(json.dumps({"key": "value"}), "reqs.json")
        assert err is not None

    def test_empty_array_returns_error(self):
        reqs, err = parse_requirements_file("[]", "reqs.json")
        assert err is not None

    def test_filters_empty_strings(self):
        data = ["", "   ", "The system shall allow login with email and password."]
        reqs, err = parse_requirements_file(json.dumps(data), "reqs.json")
        assert err is None
        assert len(reqs) == 1


# parse_requirements_file() — unsupported

class TestParseRequirementsFileUnsupported:

    def test_unsupported_extension_returns_error(self):
        reqs, err = parse_requirements_file("some content", "reqs.csv")
        assert err is not None
        assert reqs == []

    def test_pdf_extension_returns_error(self):
        reqs, err = parse_requirements_file("some content", "reqs.pdf")
        assert err is not None


# ProcessedRequirement

class TestProcessedRequirement:

    def _make(self):
        return ProcessedRequirement(
            original_text="Users should be able to login.",
            final_text="The system shall authenticate users via secure login.",
            req_type="functional",
            category="authentication",
            category_label="User Authentication",
            smart_score=4,
            was_rewritten=True,
            was_split=False,
        )

    def test_to_dict_keys(self):
        assert set(self._make().to_dict().keys()) == {
            "original_text", "final_text", "req_type", "category",
            "category_label", "smart_score", "was_rewritten", "was_split",
        }

    def test_was_rewritten_reflected(self):
        assert self._make().to_dict()["was_rewritten"] is True

    def test_smart_score_reflected(self):
        assert self._make().to_dict()["smart_score"] == 4


# PreprocessResult

class TestPreprocessResult:

    def test_to_dict_keys(self):
        assert set(PreprocessResult().to_dict().keys()) == {
            "requirements", "domains_found", "nfr_categories_found",
            "total_input", "total_output", "rewritten_count", "split_count", "error",
        }

    def test_default_error_is_none(self):
        assert PreprocessResult().to_dict()["error"] is None


# _fallback_batch()

class TestFallbackBatch:

    def test_returns_one_per_input(self):
        pp = RequirementPreprocessor(_StubProvider())
        results = pp._fallback_batch([
            "The system shall allow login.",
            "The system shall support password reset.",
        ])
        assert len(results) == 2

    def test_preserves_original_text(self):
        pp = RequirementPreprocessor(_StubProvider())
        results = pp._fallback_batch(["The system shall allow login."])
        assert results[0].original_text == "The system shall allow login."
        assert results[0].final_text    == "The system shall allow login."

    def test_defaults_to_functional(self):
        pp = RequirementPreprocessor(_StubProvider())
        assert pp._fallback_batch(["Some requirement text here."])[0].req_type == "functional"

    def test_default_category_is_general(self):
        pp = RequirementPreprocessor(_StubProvider())
        assert pp._fallback_batch(["Some requirement text here."])[0].category == "general"


# process() — with stub LLM

class TestProcessWithStubLLM:

    def _two_reqs(self):
        return [
            "The system shall allow user login with email and password.",
            "The system shall respond within 200ms for 95% of API requests.",
        ]

    def test_empty_list_returns_error(self):
        pp = RequirementPreprocessor(_StubProvider())
        assert pp.process([]).error is not None

    def test_returns_preprocessresult(self):
        reqs  = self._two_reqs()
        items = [_llm_item(r) for r in reqs]
        pp    = RequirementPreprocessor(_StubProvider(response_json=items))
        assert isinstance(pp.process(reqs), PreprocessResult)

    def test_total_input_correct(self):
        reqs  = self._two_reqs()
        items = [_llm_item(r) for r in reqs]
        pp    = RequirementPreprocessor(_StubProvider(response_json=items))
        assert pp.process(reqs).total_input == 2

    def test_deduplicates_identical_final_text(self):
        reqs      = self._two_reqs()
        same_text = "The system shall authenticate users."
        items     = [_llm_item(reqs[0], final=same_text),
                     _llm_item(reqs[1], final=same_text)]
        pp        = RequirementPreprocessor(_StubProvider(response_json=items))
        assert pp.process(reqs).total_output == 1

    def test_rewritten_count(self):
        reqs  = self._two_reqs()
        items = [_llm_item(reqs[0], was_rewritten=True),
                 _llm_item(reqs[1], was_rewritten=False)]
        pp    = RequirementPreprocessor(_StubProvider(response_json=items))
        assert pp.process(reqs).rewritten_count == 1

    def test_collects_domains(self):
        reqs  = ["The system shall allow user login."]
        items = [_llm_item(reqs[0], req_type="functional",
                           category="authentication",
                           category_label="User Authentication")]
        pp    = RequirementPreprocessor(_StubProvider(response_json=items))
        assert "User Authentication" in pp.process(reqs).domains_found

    def test_collects_nfr_categories(self):
        reqs  = ["The system shall respond within 200ms."]
        items = [_llm_item(reqs[0], req_type="non_functional",
                           category="performance",
                           category_label="Performance")]
        pp    = RequirementPreprocessor(_StubProvider(response_json=items))
        assert "performance" in pp.process(reqs).nfr_categories_found

    def test_falls_back_on_llm_failure(self):
        pp     = RequirementPreprocessor(_StubProvider(raise_exc=True))
        result = pp.process(["The system shall allow user login with email."])
        assert result.total_output >= 1

    def test_falls_back_on_empty_llm_response(self):
        pp     = RequirementPreprocessor(_StubProvider(response_json=[]))
        result = pp.process(["The system shall allow user login with email."])
        assert result.total_output >= 1


# Factory

def test_create_preprocessor_returns_instance():
    assert isinstance(create_preprocessor(_StubProvider()), RequirementPreprocessor)