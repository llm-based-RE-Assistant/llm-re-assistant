from __future__ import annotations
import re
from dataclasses import dataclass
from src.components.conversation_state import RequirementType

_PATTERN_REQ_TAG = re.compile(
    r'<REQ\b'
    r'(?=[^>]*\btype=["\'](?P<type>functional|non_functional|non-functional|constraint|nfr)["\'])'
    r'(?=[^>]*\bcategory=["\'](?P<category>[^"\']+)["\'])'
    r'[^>]*>\s*(?P<text>.*?)\s*</REQ>',
    re.DOTALL | re.IGNORECASE)
_PATTERN_EXPLICIT = re.compile(
    r'(?:\*\*)?Requirement\s+\d+\s*\(([^)]+)\)\s*:?\*?\*?\s*([^\n]+)', re.IGNORECASE)
_PATTERN_SHALL = re.compile(
    r'(?:The\s+(?:system|app|application|user|platform)\s+shall|Users?\s+shall)\s+'
    r'([^\n.]{10,200}[.!?]?)', re.IGNORECASE)

_PATTERN_SECTION_TAG = re.compile(
    r'<SECTION\s+id=["\']([^"\']+)["\']\s*>'
    r'\s*(.*?)\s*</SECTION>', re.DOTALL | re.IGNORECASE)

@dataclass
class ExtractedReq:
    text: str
    req_type: str
    category: str
    raw_excerpt: str
    source: str
    domain_label: str = ""

_VALID_TYPES = {"functional","non_functional","non-functional","constraint","nfr"}

def _norm_type(raw):
    t = raw.strip().lower().replace("-","_")
    if t in ("nfr","non_functional"): return "non_functional"
    return t if t in _VALID_TYPES else "functional"

def _norm_category(raw):
    return raw.strip().lower().replace(" ","_").replace("-","_")

def _clean(text):
    text = re.sub(r'\s+',' ',text.strip())
    return re.sub(r'^[\-\*•]\s*','',text)


class RequirementExtractor:
    def __init__(self, min_text_length=15):
        self.min_text_length = min_text_length

    def extract(self, assistant_response):
        results, seen = [], set()
        def _add(req):
            key = re.sub(r'\s+',' ',req.text.strip().lower())
            if key not in seen and len(req.text.strip()) >= self.min_text_length:
                seen.add(key); results.append(req)

        tag_matches = list(_PATTERN_REQ_TAG.finditer(assistant_response))
        for m in tag_matches:
            raw_type = m.group('type')
            raw_cat  = m.group('category')
            raw_text = m.group('text')
            rt  = _norm_type(raw_type)
            cat = _norm_category(raw_cat)
            text = _clean(raw_text)
            excerpt = f'<REQ type="{raw_type}" category="{raw_cat}">\n{raw_text.strip()}\n</REQ>'
            _add(ExtractedReq(text=text,req_type=rt,category=cat,raw_excerpt=excerpt,source="tag"))
        tags = tag_matches  # keep the truthy check below working

        if not tags:
            for m in _PATTERN_EXPLICIT.finditer(assistant_response):
                text = _clean(m.group(2).rstrip("*").strip())
                _add(ExtractedReq(text=text,req_type=_norm_type(m.group(1)),
                     category=cat,raw_excerpt=m.group(0).strip(),source="pattern"))

        if not tags and not any(r.source=="pattern" for r in results):
            for m in _PATTERN_SHALL.finditer(assistant_response):
                text = _clean(m.group(0).strip())
                _add(ExtractedReq(text=text,req_type="functional",
                     category=cat,raw_excerpt=text,source="shall"))
        return results

    def match_domains(self, extracted, gate):
        """Fallback domain matching using the REQ category tag.
        Primary matching is done via LLM in ConversationManager."""
        if gate is None or not gate.seeded: return
        for req in extracted:
            if req.domain_label: continue  # already matched by LLM
            # Try matching the category from the REQ tag to a domain key
            cat_lower = req.category.lower().replace(" ","_").replace("-","_")
            for key in gate.domains:
                if cat_lower and (cat_lower in key or key in cat_lower):
                    req.domain_label = key; break

    def commit(self, extracted, state):
        existing = {re.sub(r'\s+',' ',r.text.strip().lower()) for r in state.requirements.values()}
        added = []
        for ext in extracted:
            key = re.sub(r'\s+',' ',ext.text.strip().lower())
            if key in existing: continue
            rt = (RequirementType.FUNCTIONAL if ext.req_type=="functional" else
                  RequirementType.NON_FUNCTIONAL if ext.req_type=="non_functional" else
                  RequirementType.CONSTRAINT)
            req = state.add_requirement(req_type=rt, text=ext.text, category=ext.category,
                                        raw_excerpt=ext.raw_excerpt, domain_key=ext.domain_label,
                                        source="elicited")
            added.append(req.req_id); existing.add(key)
        return added

    # IT8: Phase 4 section extraction
    def extract_sections(self, assistant_response: str) -> list[tuple[str, str]]:
        """
        Parse <SECTION id="X.Y">content</SECTION> tags from Phase 4 responses.
        Returns a list of (section_id, content) tuples.
        Section IDs match IEEE-830 numbering: "1.2", "2.1", "2.3", "3.1.1" etc.
        """
        found = []
        for m in _PATTERN_SECTION_TAG.finditer(assistant_response):
            section_id = m.group(1).strip()
            content = m.group(2).strip()
            if section_id and len(content) >= 20:
                found.append((section_id, content))
        return found

    def commit_sections(self, sections: list[tuple[str, str]], state) -> list[str]:
        """
        Store extracted section content into state.srs_section_content and
        mark the section as covered in state.phase4_sections_covered.
        Returns list of section IDs that were newly stored.
        """
        stored = []
        for section_id, content in sections:
            # Append to existing content if already partially filled
            if section_id in state.srs_section_content:
                existing = state.srs_section_content[section_id]
                # Only append if meaningfully different (avoids duplicate answers)
                if content.lower()[:80] not in existing.lower():
                    state.srs_section_content[section_id] = existing + "\n\n" + content
            else:
                state.srs_section_content[section_id] = content
            state.phase4_sections_covered.add(section_id)
            stored.append(section_id)
        return stored


def create_extractor():
    return RequirementExtractor()