"""
Unit tests for RequirementExtractor.

Tests cover:
- <REQ> tag parsing (type, category, text extraction)
- Fallback to explicit "Requirement N (Type):" pattern
- Fallback to "The system shall ..." pattern
- Deduplication across multiple calls
- commit() adds to ConversationState correctly
- <SECTION> tag extraction (extract_sections)
- commit_sections() stores and appends correctly
- match_domains() fallback string matching
- Edge cases: malformed tags, short text, empty input
"""

import sys
import types

# Stubs — register BEFORE importing any src module
# Only stub modules that have heavy transitive deps we can't satisfy easily.
# requirement_extractor.py only imports RequirementType from conversation_state,
# so we just need to make sure that import resolves correctly.

# Stub utils constant needed by domain_gate (may be imported transitively)
if "src.components.domain_discovery.utils" not in sys.modules:
    _du = types.ModuleType("src.components.domain_discovery.utils")
    _du._DOMAIN_GATE_COVERAGE_FRACTION = 0.8
    sys.modules["src.components.domain_discovery.utils"] = _du

# Now import real classes
from src.components.conversation_state import RequirementType          # noqa: E402
from src.components.requirement_extractor import (                     # noqa: E402
    RequirementExtractor, ExtractedReq, create_extractor,
)


# Helpers

def _extractor():
    return RequirementExtractor(min_text_length=15)


def _req_tag(req_type="functional", category="auth",
             text="The system shall authenticate users via OAuth2."):
    return f'<REQ type="{req_type}" category="{category}">\n{text}\n</REQ>'


def _section_tag(section_id="2.1",
                 content="This system is a web-based platform for managing tasks."):
    return f'<SECTION id="{section_id}">\n{content}\n</SECTION>'


class _MockState:
    """Minimal stand-in for ConversationState."""

    def __init__(self):
        self.requirements = {}
        self.turns = [type("T", (), {"requirements_added": []})()]
        self._fr = self._nfr = self._con = 0
        self.srs_section_content = {}
        self.phase4_sections_covered = set()

    def add_requirement(self, req_type, text, category, raw_excerpt="",
                        is_ambiguous=False, ambiguity_note="",
                        domain_key="", source="elicited"):
        if req_type == RequirementType.FUNCTIONAL:
            self._fr += 1; rid = f"FR-{self._fr:03d}"
        elif req_type == RequirementType.NON_FUNCTIONAL:
            self._nfr += 1; rid = f"NFR-{self._nfr:03d}"
        else:
            self._con += 1; rid = f"CON-{self._con:03d}"
        req = type("R", (), {"req_id": rid, "text": text})()
        self.requirements[rid] = req
        self.turns[-1].requirements_added.append(rid)
        return req


class _MockGate:
    def __init__(self, seeded=True, domains=None):
        self.seeded  = seeded
        self.domains = domains or {}


# REQ tag extraction

class TestReqTagExtraction:

    def test_extracts_single_functional_req(self):
        ex = _extractor()
        results = ex.extract(_req_tag("functional", "authentication",
                             "The system shall authenticate users via OAuth2."))
        assert len(results) == 1
        assert results[0].req_type == "functional"
        assert results[0].category == "authentication"

    def test_extracts_non_functional_req(self):
        ex = _extractor()
        results = ex.extract(_req_tag("non_functional", "performance",
                             "The system shall respond within 200ms for 95% of requests."))
        assert len(results) == 1
        assert results[0].req_type == "non_functional"

    def test_nfr_alias_normalized(self):
        ex = _extractor()
        results = ex.extract(_req_tag("nfr", "security_privacy",
                             "The system shall encrypt all data at rest using AES-256."))
        assert results[0].req_type == "non_functional"

    def test_non_functional_hyphen_normalized(self):
        ex = _extractor()
        results = ex.extract(_req_tag("non-functional", "reliability",
                             "The system shall achieve 99.9% uptime measured monthly."))
        assert results[0].req_type == "non_functional"

    def test_extracts_constraint(self):
        ex = _extractor()
        results = ex.extract(_req_tag("constraint", "constraints",
                             "The system shall be deployed on AWS infrastructure only."))
        assert results[0].req_type == "constraint"

    def test_extracts_multiple_tags(self):
        ex = _extractor()
        response = (
            _req_tag("functional", "auth", "The system shall allow user login with email.") +
            "\n" +
            _req_tag("non_functional", "performance",
                     "The system shall load pages within 2 seconds.")
        )
        assert len(ex.extract(response)) == 2

    def test_source_is_tag(self):
        ex = _extractor()
        results = ex.extract(_req_tag())
        assert results[0].source == "tag"

    def test_category_normalized(self):
        ex = _extractor()
        results = ex.extract(_req_tag("functional", "User Authentication",
                             "The system shall support multi-factor authentication."))
        assert results[0].category == "user_authentication"

    def test_deduplicates_identical_text(self):
        ex = _extractor()
        text = "The system shall authenticate users via OAuth2."
        response = _req_tag("functional", "auth", text) + "\n" + \
                   _req_tag("functional", "auth", text)
        assert len(ex.extract(response)) == 1

    def test_too_short_text_excluded(self):
        ex = _extractor()
        results = ex.extract(_req_tag("functional", "auth", "Login."))
        assert len(results) == 0

    def test_empty_response_returns_empty(self):
        assert _extractor().extract("") == []


# Fallback patterns

class TestFallbackPatterns:

    def test_explicit_pattern_fallback(self):
        ex = _extractor()
        response = (
            "Requirement 1 (functional): "
            "The system shall support password reset via email link."
        )
        results = ex.extract(response)
        assert len(results) >= 1

    def test_shall_pattern_fallback(self):
        ex = _extractor()
        response = (
            "The system shall support multiple user roles "
            "including admin and viewer."
        )
        results = ex.extract(response)
        assert len(results) >= 1

    def test_tag_takes_priority_over_shall(self):
        ex = _extractor()
        response = (
            _req_tag("functional", "auth",
                     "The system shall authenticate users.") +
            "\nThe system shall also log all failed login attempts for auditing."
        )
        results = ex.extract(response)
        sources = {r.source for r in results}
        assert "tag" in sources
        assert "shall" not in sources


# commit()

class TestCommit:

    def test_commit_adds_to_state(self):
        ex = _extractor()
        state = _MockState()
        extracted = ex.extract(_req_tag("functional", "auth",
                               "The system shall allow users to log in securely."))
        added = ex.commit(extracted, state)
        assert len(added) == 1
        assert added[0].startswith("FR-")

    def test_commit_skips_duplicates(self):
        ex = _extractor()
        state = _MockState()
        text = "The system shall allow users to log in securely."
        extracted = ex.extract(_req_tag("functional", "auth", text))
        ex.commit(extracted, state)
        extracted2 = ex.extract(_req_tag("functional", "auth", text))
        assert len(ex.commit(extracted2, state)) == 0

    def test_commit_nfr_gets_nfr_id(self):
        ex = _extractor()
        state = _MockState()
        extracted = ex.extract(_req_tag("non_functional", "performance",
                               "The system shall respond within 500ms under normal load."))
        added = ex.commit(extracted, state)
        assert added[0].startswith("NFR-")

    def test_commit_constraint_gets_con_id(self):
        ex = _extractor()
        state = _MockState()
        extracted = ex.extract(_req_tag("constraint", "constraints",
                               "The system shall only be deployed on approved cloud providers."))
        added = ex.commit(extracted, state)
        assert added[0].startswith("CON-")


# Section tag extraction

class TestSectionExtraction:

    def test_extracts_single_section(self):
        ex = _extractor()
        response = _section_tag(
            "2.1",
            "This system provides a web-based task management platform for teams."
        )
        sections = ex.extract_sections(response)
        assert len(sections) == 1
        assert sections[0][0] == "2.1"

    def test_extracts_multiple_sections(self):
        ex = _extractor()
        response = (
            _section_tag("1.2",
                         "The scope of this system includes task creation and management.") +
            "\n" +
            _section_tag("2.3",
                         "Primary users are project managers and team members in SMEs.")
        )
        sections = ex.extract_sections(response)
        assert len(sections) == 2
        ids = [s[0] for s in sections]
        assert "1.2" in ids
        assert "2.3" in ids

    def test_short_content_excluded(self):
        ex = _extractor()
        sections = ex.extract_sections(_section_tag("2.1", "Short."))
        assert len(sections) == 0

    def test_empty_response_returns_no_sections(self):
        assert _extractor().extract_sections("") == []


# commit_sections()

class TestCommitSections:

    def test_stores_section_content(self):
        ex = _extractor()
        state = _MockState()
        content = "This system provides task management for distributed teams."
        ex.commit_sections([("2.1", content)], state)
        assert state.srs_section_content["2.1"] == content
        assert "2.1" in state.phase4_sections_covered

    def test_appends_new_content(self):
        ex = _extractor()
        state = _MockState()
        state.srs_section_content["2.1"] = "Original content about system purpose."
        new = "Additional details about deployment environment and user base."
        ex.commit_sections([("2.1", new)], state)
        assert "Original content" in state.srs_section_content["2.1"]
        assert "Additional details" in state.srs_section_content["2.1"]

    def test_does_not_duplicate_identical_content(self):
        ex = _extractor()
        state = _MockState()
        content = "This system provides task management for distributed teams globally."
        state.srs_section_content["2.1"] = content
        ex.commit_sections([("2.1", content[:80])], state)
        assert state.srs_section_content["2.1"] == content

    def test_marks_section_as_covered(self):
        ex = _extractor()
        state = _MockState()
        ex.commit_sections(
            [("2.3", "Users are project managers and team leads in companies.")],
            state
        )
        assert "2.3" in state.phase4_sections_covered


# match_domains()

class TestMatchDomains:

    def test_matches_by_category_substring(self):
        ex = _extractor()
        extracted = [ExtractedReq(
            text="The system shall authenticate users.",
            req_type="functional",
            category="authentication",
            raw_excerpt="",
            source="tag",
            domain_label="",
        )]
        gate = _MockGate(seeded=True, domains={"user_authentication": None})
        ex.match_domains(extracted, gate)
        assert extracted[0].domain_label == "user_authentication"

    def test_skips_already_matched(self):
        ex = _extractor()
        extracted = [ExtractedReq(
            text="The system shall authenticate users via LDAP.",
            req_type="functional",
            category="authentication",
            raw_excerpt="",
            source="tag",
            domain_label="pre_matched",
        )]
        gate = _MockGate(seeded=True, domains={"user_authentication": None})
        ex.match_domains(extracted, gate)
        assert extracted[0].domain_label == "pre_matched"

    def test_no_match_when_gate_not_seeded(self):
        ex = _extractor()
        extracted = [ExtractedReq(
            text="The system shall authenticate users.",
            req_type="functional",
            category="authentication",
            raw_excerpt="",
            source="tag",
            domain_label="",
        )]
        gate = _MockGate(seeded=False, domains={"user_authentication": None})
        ex.match_domains(extracted, gate)
        assert extracted[0].domain_label == ""


# Factory
def test_create_extractor_returns_instance():
    assert isinstance(create_extractor(), RequirementExtractor)