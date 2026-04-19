"""
conftest.py — shared fixtures for the RE Assistant test suite.

Fixtures here are available to all test files without explicit import.
"""

import pytest
import sys
import types


# Session-scoped stub registry
# Prevents multiple test files from re-registering the same stubs
# and causing "module already registered" conflicts.

def _ensure_stub(module_name: str, attrs: dict = None):
    """Register a stub module if not already present, then patch attrs."""
    if module_name not in sys.modules:
        sys.modules[module_name] = types.ModuleType(module_name)
    if attrs:
        for k, v in attrs.items():
            setattr(sys.modules[module_name], k, v)
    return sys.modules[module_name]


# Fixtures

@pytest.fixture
def minimal_state():
    """Return a bare ConversationState with no domain gate and no turns."""
    from src.components.conversation_state import ConversationState
    state = ConversationState(session_id="test-session-001")
    state.domain_gate = None
    return state


@pytest.fixture
def seeded_gate():
    """Return a DomainGate seeded with three domains in varying states."""
    from src.components.domain_discovery.domain_gate import DomainGate
    from src.components.domain_discovery.domain_space import DomainSpec

    gate = DomainGate(seeded=True)

    auth = DomainSpec(label="User Authentication")
    auth.status = "confirmed"
    auth.req_ids = ["FR-001", "FR-002", "FR-003"]
    auth.probe_count = 2
    gate.domains["user_authentication"] = auth

    reporting = DomainSpec(label="Reporting")
    reporting.status = "partial"
    reporting.req_ids = ["FR-004"]
    reporting.probe_count = 1
    gate.domains["reporting"] = reporting

    legacy = DomainSpec(label="Legacy Module")
    legacy.status = "excluded"
    gate.domains["legacy"] = legacy

    return gate


@pytest.fixture
def extractor():
    """Return a default RequirementExtractor instance."""
    from src.components.requirement_extractor import RequirementExtractor
    return RequirementExtractor(min_text_length=15)


@pytest.fixture
def gap_detector_enabled():
    """Return a GapDetector with gap detection enabled."""
    from src.components.gap_detector import GapDetector
    return GapDetector(enabled=True)


@pytest.fixture
def gap_detector_disabled():
    """Return a GapDetector with gap detection disabled."""
    from src.components.gap_detector import GapDetector
    return GapDetector(enabled=False)