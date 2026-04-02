"""
src/components/srs_formatter.py
=================
RE Assistant — Iteration 5 | University of Hildesheim
SRS Output Formatter: renders an SRSTemplate to a readable IEEE-830 document.

Iteration 5 changes
-------------------
IT5-F1  Removed all imports of hard-coded DOMAIN_COVERAGE_GATE,
        compute_domain_gate(), gate_is_satisfied(), and related constants
        from prompt_architect.  These no longer exist in Iteration 5.

IT5-F2  _render_header() reads state.domain_gate (DomainGate object) directly
        for dual metrics.  Falls back gracefully if the gate was never seeded.

IT5-F3  _render_appendix_b() B.1.1 domain gate breakdown now iterates over
        state.domain_gate.domains (dynamic, scenario-specific) instead of
        the hard-coded DOMAIN_COVERAGE_GATE dict.

IT5-F4  _render_appendix_d() D.1 now generates generic architecture-review
        stubs for every unconfirmed dynamic domain.  The hard-coded
        DigitalHome-specific expected-requirement lists are removed.
        D.2 structural stubs and D.3 summary are updated accordingly.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from srs_template import (
    AnnotatedRequirement,
    SRSTemplate,
    SmartFlag,
    InterfaceRequirements,
    SystemAttributes,
)
from conversation_state import ConversationState, RequirementType
from prompt_architect import IEEE830_CATEGORIES, MANDATORY_NFR_CATEGORIES
from domain_discovery import NFR_CATEGORIES


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _badge(smart_score: int) -> str:
    """Return a compact quality badge string."""
    if smart_score >= 5:
        return "[★★★ 5/5]"
    elif smart_score == 4:
        return "[★★★ 4/5]"
    elif smart_score == 3:
        return "[★★☆ 3/5]"
    elif smart_score == 2:
        return "[★☆☆ 2/5]"
    else:
        return "[☆☆☆ 1/5]"


def _priority_badge(priority: str) -> str:
    return {"Must-have": "🔴", "Should-have": "🟡", "Nice-to-have": "🟢"}.get(priority, "")


def _render_req_block(ann: AnnotatedRequirement, show_smart: bool = True) -> list[str]:
    """
    Render a single AnnotatedRequirement as a list of Markdown lines.

    Format:
      **FR-001** 🔴 [★★★ 4/5]
      The system shall allow users to log in with email and password.
      > *Source: Turn 3 | Category: Functional | Section: 3.1*
      > *SMART: Specific ✓, Measurable ✗, Testable ✓, Unambiguous ✓, Relevant ✓*
      > *Notes: Lacks measurable constraint (e.g., login within N seconds).*
    """
    lines: list[str] = []
    req = ann.requirement

    priority_icon = _priority_badge(ann.priority)
    smart_str = _badge(ann.smart.score) if show_smart else ""

    # Headline
    ambiguity_flag = " ⚠️" if req.is_ambiguous else ""
    lines.append(f"**{req.req_id}** {priority_icon} {smart_str}{ambiguity_flag}")
    lines.append("")
    lines.append(req.text)
    lines.append("")

    # Metadata blockquote
    cat_label = IEEE830_CATEGORIES.get(req.category, req.category)
    lines.append(f"> *Source: Turn {req.turn_id} | Category: {cat_label} | Section §{ann.ieee_section}*")

    if show_smart:
        # SMART dimension summary
        def _dim(flag: SmartFlag, label: str) -> str:
            if flag in ann.smart.satisfied:
                return f"{label} ✓"
            elif flag in ann.smart.violated:
                return f"{label} ✗"
            return f"{label} ?"

        dims = ", ".join([
            _dim(SmartFlag.SPECIFIC,    "Specific"),
            _dim(SmartFlag.MEASURABLE,  "Measurable"),
            _dim(SmartFlag.TESTABLE,    "Testable"),
            _dim(SmartFlag.UNAMBIGUOUS, "Unambiguous"),
            _dim(SmartFlag.RELEVANT,    "Relevant"),
        ])
        lines.append(f"> *SMART: {dims}*")

        if ann.smart.notes:
            lines.append(f"> *⚠️ {ann.smart.notes}*")

    if req.ambiguity_note:
        lines.append(f"> *🔍 Ambiguity note: {req.ambiguity_note}*")

    lines.append("")
    return lines


def _section_divider(title: str) -> list[str]:
    return ["---", "", f"## {title}", ""]


def _subsection(title: str) -> list[str]:
    return [f"### {title}", ""]


def _subsubsection(title: str) -> list[str]:
    return [f"#### {title}", ""]


def _empty_section_note(msg: str = "") -> list[str]:
    note = msg or "*Not elicited during this session.*"
    return [note, ""]


def _coverage_tick(covered: bool) -> str:
    return "✅" if covered else "❌"


# ---------------------------------------------------------------------------
# SRSFormatter
# ---------------------------------------------------------------------------

class SRSFormatter:
    """
    Renders an SRSTemplate into readable output formats.

    Usage
    -----
    formatter = SRSFormatter()
    md = formatter.to_markdown(template, state)
    path = formatter.write(template, state, output_dir)
    """

    def __init__(self, show_smart: bool = True, show_transcript_summary: bool = True):
        """
        Parameters
        ----------
        show_smart              : Include SMART quality badges and notes.
        show_transcript_summary : Include Appendix C (conversation summary).
        """
        self.show_smart = show_smart
        self.show_transcript_summary = show_transcript_summary

    # ------------------------------------------------------------------
    # Public rendering methods
    # ------------------------------------------------------------------

    def to_markdown(self, template: SRSTemplate, state: ConversationState) -> str:
        """Render a complete IEEE-830 Markdown SRS document."""
        lines: list[str] = []

        self._render_header(lines, template, state)
        self._render_section1(lines, template, state)
        self._render_section2(lines, template, state)
        self._render_section3(lines, template, state)
        self._render_open_issues(lines, template)
        self._render_appendix_a(lines, template)
        self._render_appendix_b(lines, template, state)
        self._render_appendix_d(lines, template, state)   # NEW: Priority 4
        if self.show_transcript_summary:
            self._render_appendix_c(lines, state)

        return "\n".join(lines)

    def to_plain_text(self, template: SRSTemplate, state: ConversationState) -> str:
        """
        Evaluator-friendly plain text version.
        Strips Markdown formatting, keeps requirement text and IDs.
        """
        md = self.to_markdown(template, state)
        # Strip Markdown emphasis and headings — keep content readable
        import re
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", md)   # bold
        text = re.sub(r"\*(.*?)\*",     r"\1", text)  # italic
        text = re.sub(r"^#{1,6}\s+",    "",    text, flags=re.MULTILINE)  # headings
        text = re.sub(r"^>\s*",         "",    text, flags=re.MULTILINE)  # blockquotes
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links
        text = re.sub(r"^---$",         "─" * 60, text, flags=re.MULTILINE)
        return text

    def write(
        self,
        template: SRSTemplate,
        state: ConversationState,
        output_dir: Path,
        filename: Optional[str] = None,
    ) -> Path:
        """
        Write the Markdown SRS to disk.

        Returns the path of the written file.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        if filename is None:
            ts = time.strftime("%Y%m%d_%H%M%S")
            filename = f"SRS_{template.session_id}_{ts}.md"
        path = output_dir / filename
        content = self.to_markdown(template, state)
        path.write_text(content, encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    # Header  (Iteration 5: dual metrics from state.domain_gate — IT5-F2)
    # ------------------------------------------------------------------

    def _render_header(
        self, lines: list[str], template: SRSTemplate, state: ConversationState
    ) -> None:
        w = lines.append
        w("# Software Requirements Specification")
        w(f"## {template.project_name}")
        w("")
        w("| Field | Value |")
        w("|-------|-------|")
        w("| Standard | IEEE 830-1998 (adapted) |")
        w("| Version | v0.1 — Draft |")
        w("| Status | Generated by RE Assistant Iteration 5 |")
        w(f"| Session ID | `{template.session_id}` |")
        w(f"| Created | {template.created_at} |")
        w(f"| Last Updated | {template.last_updated_at} |")
        w(f"| Elicitation Turns | {state.turn_count} |")
        w(
            f"| Requirements | {template.total_requirements} total "
            f"({template.functional_count} FR, {template.nfr_count} NFR) |"
        )
        w(f"| Avg SMART Score | {template.avg_smart_score} / 5 |")

        # ── IT5-F2: dual metrics from DomainGate ────────────────────────
        gate = state.domain_gate
        if gate is not None and gate.seeded and gate.total > 0:
            done_count  = gate.done_count
            total_count = gate.total
            domain_pct  = gate.completeness_pct
        else:
            done_count = total_count = domain_pct = 0

        ieee_pct = state.coverage_percentage
        w(
            f"| Domain Completeness Score | {done_count}/{total_count} "
            f"({domain_pct}%) — functional domains confirmed or excluded |"
        )
        w(
            f"| IEEE-830 Elicitation Coverage | "
            f"{len(state.covered_categories)}/{len(IEEE830_CATEGORIES)} "
            f"({ieee_pct}%) — structural categories covered |"
        )
        w("")

        # Quality summary bar
        if template.total_requirements > 0:
            w("> **Quality Summary**")
            w(f"> ✅ High Quality (4–5/5): {template.high_quality_count} requirements")
            w(
                f"> ⚠️  Acceptable (3/5): "
                f"{template.total_requirements - template.high_quality_count - template.needs_improvement_count}"
                f" requirements"
            )
            w(f"> ❌ Needs Improvement (<3/5): {template.needs_improvement_count} requirements")
            w("")

        # Domain gate incompleteness warning
        if gate is not None and gate.seeded and not gate.is_satisfied:
            unprobed = [
                d.label for d in gate.domains.values()
                if d.status in ("unprobed", "partial")
            ]
            if unprobed:
                w(
                    f"> ⚠️ **INCOMPLETE ELICITATION — "
                    f"{len(unprobed)} functional domain(s) were not fully elicited:**"
                )
                for label in unprobed:
                    w(f"> - {label}")
                w(
                    "> Requirements in these areas may be incomplete. "
                    "See Appendix D for design-derived placeholders."
                )
                w("")

        # Missing mandatory NFRs
        report = state.get_coverage_report()
        if report["missing_mandatory_nfrs"]:
            w("> ⚠️ **WARNING — Mandatory NFR Categories Not Elicited:**")
            for cat in report["missing_mandatory_nfrs"]:
                w(f"> - {cat}")
            w("")

        if template.open_issues:
            w(
                f"> 🔍 **{len(template.open_issues)} open issue(s) require "
                "stakeholder clarification** — see Open Issues section."
            )
            w("")
        if template.conflicts:
            w(f"> ⛔ **{len(template.conflicts)} conflict(s) detected** — review before development.")
            w("")

    # ------------------------------------------------------------------
    # §1 Introduction
    # ------------------------------------------------------------------

    def _render_section1(
        self, lines: list[str], template: SRSTemplate, state: ConversationState
    ) -> None:
        lines += _section_divider("1. Introduction")
        s1 = template.section1

        lines += _subsection("1.1 Purpose")
        if s1.purpose:
            lines.append(s1.purpose)
        else:
            lines.append(
                f"This document specifies the software requirements for "
                f"**{template.project_name}**. It was generated by the RE Assistant "
                f"through a structured {state.turn_count}-turn elicitation session and serves "
                f"as the primary reference for development, testing, and stakeholder validation."
            )
        lines.append("")

        lines += _subsection("1.2 Scope")
        if s1.scope:
            lines.append(s1.scope)
        else:
            lines.append(
                f"**{template.project_name}** is the system described in this document. "
                f"Requirements were elicited via a conversational session with the RE Assistant."
            )
        lines.append("")

        lines += _subsection("1.3 Definitions, Acronyms, Abbreviations")
        lines.append("| Term | Definition |")
        lines.append("|------|------------|")
        # Always include standard terms
        standard_defs = {
            "FR":  "Functional Requirement",
            "NFR": "Non-Functional Requirement",
            "CON": "Constraint",
            "SRS": "Software Requirements Specification",
            "IEEE 830": "IEEE Standard for Software Requirements Specifications (1998)",
            "SMART": "Specific, Measurable, Achievable, Relevant, Testable",
        }
        all_defs = {**standard_defs, **s1.definitions}
        for term, defn in all_defs.items():
            lines.append(f"| {term} | {defn} |")
        lines.append("")

        lines += _subsection("1.4 References")
        if s1.references:
            for ref in s1.references:
                lines.append(f"- {ref}")
        else:
            lines.append("- IEEE 830-1998: IEEE Recommended Practice for Software Requirements Specifications")
            lines.append(f"- Session log: `logs/session_{template.session_id}.json`")
        lines.append("")

        lines += _subsection("1.5 Overview")
        lines.append(
            "This document follows the IEEE 830-1998 structure. "
            "Section 2 provides an overall description of the system. "
            "Section 3 contains the specific functional and non-functional requirements. "
            "Appendices provide traceability, quality metrics, and elicitation coverage data."
        )
        lines.append("")

    # ------------------------------------------------------------------
    # §2 Overall Description
    # ------------------------------------------------------------------

    def _render_section2(
        self, lines: list[str], template: SRSTemplate, state: ConversationState
    ) -> None:
        lines += _section_divider("2. Overall Description")
        s2 = template.section2

        lines += _subsection("2.1 Product Perspective")
        if s2.product_perspective:
            lines.append(s2.product_perspective)
        elif state.covered_categories & {"purpose", "scope"}:
            lines.append(
                f"*{template.project_name}* is a standalone software system. "
                f"See session log `session_{template.session_id}.json` for elicitation context."
            )
        else:
            lines.append("*Product perspective not fully elicited. See conversation log.*")
        lines.append("")

        lines += _subsection("2.2 Product Functions")
        if s2.product_functions:
            for fn in s2.product_functions:
                lines.append(f"- {fn}")
        elif template.section3.functional:
            # Derive from FR list
            lines.append("The following high-level functions were elicited (see §3.1 for full detail):")
            for ann in template.section3.functional[:6]:
                lines.append(f"- {ann.text[:100]}{'...' if len(ann.text) > 100 else ''}")
        else:
            lines += _empty_section_note()
        lines.append("")

        lines += _subsection("2.3 User Characteristics")
        if s2.user_classes:
            lines.append("| User Class | Description | Proficiency |")
            lines.append("|------------|-------------|-------------|")
            for uc in s2.user_classes:
                lines.append(f"| {uc.name} | {uc.description} | {uc.proficiency or 'Not specified'} |")
        else:
            # Fall back to stakeholder requirements
            stakeholder_reqs = [
                ann for ann in template.annotated_reqs.values()
                if ann.requirement.category == "stakeholders"
            ]
            if stakeholder_reqs:
                for ann in stakeholder_reqs:
                    lines.append(f"- {ann.text} *(Turn {ann.turn_id})*")
            else:
                lines += _empty_section_note("*Stakeholder roles not formally elicited. See conversation log.*")
        lines.append("")

        lines += _subsection("2.4 General Constraints")
        constraint_reqs = template.section3.design_constraints
        if s2.general_constraints or constraint_reqs:
            for c in s2.general_constraints:
                lines.append(f"- {c}")
            for ann in constraint_reqs:
                lines.append(f"- **{ann.req_id}**: {ann.text} *(Turn {ann.turn_id})*")
        else:
            lines += _empty_section_note()
        lines.append("")

        lines += _subsection("2.5 Assumptions and Dependencies")
        if s2.assumptions:
            for a in s2.assumptions:
                lines.append(f"- {a}")
        else:
            lines.append("- To be confirmed with stakeholders during requirements review.")
        lines.append("")

         # §2.4 and §2.6 — rendered from sentinel items stored by SRSCoverageEnricher
        from srs_coverage import render_section2_extras
        render_section2_extras(lines, template)

    # ------------------------------------------------------------------
    # §3 Specific Requirements
    # ------------------------------------------------------------------

    def _render_section3(
        self, lines: list[str], template: SRSTemplate, state: ConversationState
    ) -> None:
        lines += _section_divider("3. Specific Requirements")
        self._render_s31_functional(lines, template)
        self._render_s32_interfaces(lines, template)
        self._render_s33_performance(lines, template)
        self._render_s34_database(lines, template)
        self._render_s35_constraints(lines, template)
        self._render_s36_attributes(lines, template)

    def _render_s31_functional(self, lines: list[str], template: SRSTemplate) -> None:
        lines += _subsection("3.1 Functional Requirements")
        frs = template.section3.functional
        if frs:
            for ann in frs:
                lines += _render_req_block(ann, self.show_smart)
        else:
            lines += _empty_section_note(
                "*No functional requirements were formally extracted. "
                "Functional elicitation occurred conversationally — see session log. "
                "Automatic extraction will be implemented in Iteration 3.*"
            )
        lines.append("")

    def _render_s32_interfaces(self, lines: list[str], template: SRSTemplate) -> None:
        lines += _subsection("3.2 External Interface Requirements")
        iface = template.section3.interfaces

        def _iface_sub(title: str, items: list[str]) -> None:
            lines.extend(_subsubsection(title))
            if items:
                for item in items:
                    lines.append(f"- {item}")
            else:
                # After srs_coverage enrichment, items may contain a single long
                # prose block (not a simple bullet list).  Detect and render correctly.
                lines.append("*Not elicited.*")
            lines.append("")

        _iface_sub("3.2.1 User Interfaces", iface.user_interfaces)
        _iface_sub("3.2.2 Hardware Interfaces", iface.hardware_interfaces)
        _iface_sub("3.2.3 Software Interfaces", iface.software_interfaces)
        _iface_sub("3.2.4 Communication Interfaces", iface.communication_interfaces)

    def _render_s33_performance(self, lines: list[str], template: SRSTemplate) -> None:
        lines += _subsection("3.3 Performance Requirements")
        perf = template.section3.performance
        covered = "performance" in (
            ann.requirement.category for ann in template.annotated_reqs.values()
        )
        if perf:
            for ann in perf:
                lines += _render_req_block(ann, self.show_smart)
        elif covered:
            lines += _empty_section_note(
                "*Performance was discussed (see log) but no formal NFR was extracted.*"
            )
        else:
            lines.append("⚠️ **NOT ELICITED** — Performance is a mandatory NFR category.")
            lines.append("")

    def _render_s34_database(self, lines: list[str], template: SRSTemplate) -> None:
        lines += _subsection("3.4 Logical Database Requirements")
        if template.section3.database:
            for d in template.section3.database:
                lines.append(f"- {d}")
        else:
            lines += _empty_section_note()
        lines.append("")

    def _render_s35_constraints(self, lines: list[str], template: "SRSTemplate") -> None:
        lines += _subsection("3.5 Design Constraints")
        cons = template.section3.design_constraints   # list[AnnotatedRequirement]
        if cons:
            for ann in cons:
                lines += _render_req_block(ann, self.show_smart)
        else:
            # Check if srs_coverage stored a stub via the sentinel in section1.references
            from srs_coverage import render_section35_stub
            if not render_section35_stub(lines, template):
                lines += _empty_section_note()
        lines.append("")

    def _render_s36_attributes(self, lines: list[str], template: SRSTemplate) -> None:
        lines += _subsection("3.6 Software System Attributes")
        attrs = template.section3.attributes

        def _attr_block(title: str, reqs: list[AnnotatedRequirement], cat_key: str) -> None:
            lines.extend(_subsubsection(title))
            if reqs:
                for ann in reqs:
                    lines.extend(_render_req_block(ann, self.show_smart))
            elif cat_key in MANDATORY_NFR_CATEGORIES:
                lines.append(f"⚠️ **NOT ELICITED** — {IEEE830_CATEGORIES.get(cat_key, cat_key)} "
                             f"is a mandatory NFR category.")
                lines.append("")
            else:
                lines.extend(_empty_section_note())

        _attr_block("3.6.1 Reliability",     attrs.reliability,     "reliability")
        _attr_block("3.6.2 Availability",    attrs.availability,    "availability")
        _attr_block("3.6.3 Security",        attrs.security,        "security_privacy")
        _attr_block("3.6.4 Maintainability", attrs.maintainability, "maintainability")
        _attr_block("3.6.5 Portability",     attrs.portability,     "compatibility")
        _attr_block("3.6.6 Usability",       attrs.usability,       "usability")

    # ------------------------------------------------------------------
    # Open Issues
    # ------------------------------------------------------------------

    def _render_open_issues(self, lines: list[str], template: SRSTemplate) -> None:
        if not template.open_issues and not template.conflicts:
            return
        lines += _section_divider("4. Open Issues and Conflicts")

        if template.open_issues:
            lines += _subsection("4.1 Open Issues (Ambiguities requiring clarification)")
            for i, issue in enumerate(template.open_issues, 1):
                lines.append(f"{i}. {issue}")
            lines.append("")

        if template.conflicts:
            lines += _subsection("4.2 Detected Conflicts")
            lines.append(
                "> ⛔ The following contradictions were detected during elicitation. "
                "They must be resolved before development begins."
            )
            lines.append("")
            for i, conflict in enumerate(template.conflicts, 1):
                lines.append(f"{i}. {conflict}")
            lines.append("")

    # ------------------------------------------------------------------
    # Appendix A — Traceability Matrix
    # ------------------------------------------------------------------

    def _render_appendix_a(self, lines: list[str], template: SRSTemplate) -> None:
        lines += _section_divider("Appendix A — Requirement Traceability Matrix")
        lines.append(
            "| ID | Type | Category | Section | Turn | Priority | SMART | Text |"
        )
        lines.append("|-----|------|----------|---------|------|----------|-------|------|")

        all_reqs = sorted(
            template.annotated_reqs.values(), key=lambda a: a.req_id
        )
        for ann in all_reqs:
            req = ann.requirement
            cat_label = IEEE830_CATEGORIES.get(req.category, req.category)
            short_text = req.text[:70] + ("…" if len(req.text) > 70 else "")
            smart_score = f"{ann.smart.score}/5"
            lines.append(
                f"| {req.req_id} | {req.req_type.value} | {cat_label} "
                f"| §{ann.ieee_section} | T{req.turn_id} | {ann.priority} "
                f"| {smart_score} | {short_text} |"
            )
        if not all_reqs:
            lines.append("| — | — | — | — | — | — | — | No requirements extracted. |")
        lines.append("")
        lines.append(f"*Full session log: `logs/session_{template.session_id}.json`*")
        lines.append("")

    # ------------------------------------------------------------------
    # Appendix B — Coverage & Quality Report
    # ------------------------------------------------------------------

    def _render_appendix_b(
        self, lines: list[str], template: SRSTemplate, state: ConversationState
    ) -> None:
        lines += _section_divider("Appendix B — Elicitation Coverage & Quality Report")
        lines.append("*Generated by RE Assistant for evaluation purposes.*")
        lines.append("")

        report = state.get_coverage_report()

        # IT5-F3: read domain gate from state, not from hard-coded dict
        gate = state.domain_gate
        if gate is not None and gate.seeded and gate.total > 0:
            done_count  = gate.done_count
            total_count = gate.total
            domain_pct  = gate.completeness_pct
        else:
            done_count = total_count = domain_pct = 0

        lines.append("### B.1 Session Metrics")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total conversation turns | {report['turn_count']} |")
        lines.append(f"| Total requirements | {template.total_requirements} |")
        lines.append(f"| Functional requirements | {template.functional_count} |")
        lines.append(f"| Non-functional requirements | {template.nfr_count} |")
        lines.append(f"| Design constraints | {len(template.section3.design_constraints)} |")
        lines.append(
            f"| **Domain Completeness Score** | **{done_count}/{total_count} "
            f"({domain_pct}%)** — functional domains confirmed/excluded |"
        )
        lines.append(
            f"| IEEE-830 Elicitation Coverage | {report['coverage_percentage']}% "
            f"— structural categories covered |"
        )
        lines.append(f"| Mandatory NFRs fully covered | {'✅ Yes' if report['mandatory_nfrs_covered'] else '❌ No'} |")
        lines.append(f"| Open issues | {len(template.open_issues)} |")
        lines.append(f"| Detected conflicts | {len(template.conflicts)} |")
        lines.append("")

        # IT5-F3: dynamic domain gate breakdown
        lines.append("### B.1.1 Domain Coverage Gate Breakdown")
        lines.append("")
        _STATUS_LABEL = {
            "confirmed": "✅ Confirmed",
            "excluded":  "❌ Excluded (out of scope)",
            "partial":   "🔶 Partial (needs more elicitation)",
            "unprobed":  "⬜ Unprobed (never asked)",
        }
        if gate is not None and gate.seeded and gate.total > 0:
            lines.append("| Domain | Status | Requirements |")
            lines.append("|--------|--------|-------------|")
            for domain in gate.domains.values():
                req_count = len(domain.req_ids)
                status_label = _STATUS_LABEL.get(domain.status, domain.status)
                lines.append(f"| {domain.label} | {status_label} | {req_count} |")
        else:
            lines.append("*Domain gate was not seeded during this session.*")
        lines.append("")

        # NFR coverage breakdown (IT5: requirement-driven)
        lines.append("### B.1.2 NFR Coverage (Requirement-Based)")
        lines.append("")
        lines.append("| NFR Category | Requirements Extracted | Covered |")
        lines.append("|-------------|----------------------|---------|")
        for cat_key, cat_label in NFR_CATEGORIES.items():
            count    = state.nfr_coverage.get(cat_key, 0)
            covered  = "✅" if count >= 1 else "❌"
            lines.append(f"| {cat_label} | {count} | {covered} |")
        lines.append("")

        # SMART quality breakdown
        lines.append("### B.2 SMART Quality Breakdown")
        lines.append("")
        lines.append("| Quality Level | Count | % of Total |")
        lines.append("|---------------|-------|------------|")
        total = template.total_requirements or 1
        high = template.high_quality_count
        low  = template.needs_improvement_count
        mid  = total - high - low
        lines.append(f"| ✅ High Quality (4–5/5) | {high} | {round(high/total*100)}% |")
        lines.append(f"| ⚠️  Acceptable (3/5) | {mid} | {round(mid/total*100)}% |")
        lines.append(f"| ❌ Needs Improvement (<3/5) | {low} | {round(low/total*100)}% |")
        lines.append(f"| **Average SMART score** | **{template.avg_smart_score}/5** | |")
        lines.append("")

        # Per-SMART-dimension breakdown
        if template.annotated_reqs:
            lines.append("### B.3 SMART Dimension Analysis")
            lines.append("")
            from srs_template import SmartFlag
            all_anns = list(template.annotated_reqs.values())
            n = len(all_anns)
            dims = [
                (SmartFlag.SPECIFIC,    "Specific"),
                (SmartFlag.MEASURABLE,  "Measurable"),
                (SmartFlag.TESTABLE,    "Testable"),
                (SmartFlag.UNAMBIGUOUS, "Unambiguous"),
                (SmartFlag.RELEVANT,    "Relevant"),
            ]
            lines.append("| SMART Dimension | Satisfied | Violated | % Pass |")
            lines.append("|-----------------|-----------|----------|--------|")
            for flag, label in dims:
                sat = sum(1 for a in all_anns if flag in a.smart.satisfied)
                vio = sum(1 for a in all_anns if flag in a.smart.violated)
                pct = round(sat / n * 100) if n else 0
                lines.append(f"| {label} | {sat} | {vio} | {pct}% |")
            lines.append("")

        # IEEE-830 category coverage grid
        lines.append("### B.4 IEEE-830 Category Coverage")
        lines.append("")
        lines.append("| Category | Status | Mandatory NFR |")
        lines.append("|----------|--------|:-------------:|")
        for cat_key, cat_label in IEEE830_CATEGORIES.items():
            is_covered = cat_key in state.covered_categories
            is_mandatory = cat_key in MANDATORY_NFR_CATEGORIES
            tick = _coverage_tick(is_covered)
            mandatory_str = "✓" if is_mandatory else ""
            lines.append(f"| {cat_label} | {tick} {'Covered' if is_covered else 'Not Elicited'} | {mandatory_str} |")
        lines.append("")

        # Requirements needing attention
        problem_reqs = [
            ann for ann in template.annotated_reqs.values()
            if ann.smart.score < 3 or ann.requirement.is_ambiguous
        ]
        if problem_reqs:
            lines.append("### B.5 Requirements Requiring Attention")
            lines.append("")
            lines.append("The following requirements scored below 3/5 on SMART or contain flagged ambiguities:")
            lines.append("")
            lines.append("| ID | Score | Issue |")
            lines.append("|----|-------|-------|")
            for ann in problem_reqs:
                issue = ann.smart.notes or ("Ambiguity flagged" if ann.requirement.is_ambiguous else "Low SMART score")
                lines.append(f"| {ann.req_id} | {ann.smart.score}/5 | {issue[:80]} |")
            lines.append("")

    # ------------------------------------------------------------------
    # Appendix C — Conversation Transcript Summary
    # ------------------------------------------------------------------

    def _render_appendix_c(self, lines: list[str], state: ConversationState) -> None:
        lines += _section_divider("Appendix C — Conversation Transcript Summary")
        lines.append(
            "*This appendix provides a turn-by-turn summary of the elicitation session. "
            "The full raw transcript is in the session log JSON file.*"
        )
        lines.append("")

        if not state.turns:
            lines.append("*No turns recorded.*")
            lines.append("")
            return

        for turn in state.turns:
            lines.append(f"**Turn {turn.turn_id}**")
            lines.append("")

            # Truncate long messages for readability
            user_text = turn.user_message.strip()
            if len(user_text) > 200:
                user_text = user_text[:200] + "…"
            lines.append(f"> 🧑 *User:* {user_text}")
            lines.append("")

            asst_text = turn.assistant_message.strip()
            if len(asst_text) > 300:
                asst_text = asst_text[:300] + "…"
            lines.append(f"> 🤖 *Assistant:* {asst_text}")
            lines.append("")

            meta_parts: list[str] = []
            if turn.categories_updated:
                labels = [IEEE830_CATEGORIES.get(c, c) for c in turn.categories_updated]
                meta_parts.append(f"Categories newly covered: {', '.join(labels)}")
            if turn.requirements_added:
                meta_parts.append(f"Requirements added: {', '.join(turn.requirements_added)}")
            if meta_parts:
                lines.append(f"*→ {' | '.join(meta_parts)}*")
                lines.append("")


    # ------------------------------------------------------------------
    # Appendix D — Design-Derived Requirements Inventory (IT5-F4)
    # ------------------------------------------------------------------

    def _render_appendix_d(
        self, lines: list[str], template: SRSTemplate, state: ConversationState
    ) -> None:
        """
        IT5-F4: Generate design-derived stubs for unconfirmed domains
        and uncovered IEEE-830 structural sections.

        Iteration 5: stubs are generic and domain-agnostic.
        The hard-coded DigitalHome-specific expected-requirement lists
        from Iteration 4 are removed.  Each unconfirmed domain gets a
        generic stub block telling the architect what kind of requirements
        to look for, derived from the domain's label and status.
        """
        lines += _section_divider("Appendix D — Design-Derived Requirements Inventory")
        lines.append(
            "*The following entries are placeholders for requirements that a "
            "domain expert or system architect must confirm. They are tagged "
            "`[D]` (design-derived) because they could not be elicited from "
            "the stakeholder interview alone.*"
        )
        lines.append("")

        gate = state.domain_gate
        stub_count = 0

        # ── D.1 Functional Domain Stubs (dynamic) ────────────────────────
        lines.append("### D.1 Functional Domain Stubs")
        lines.append("")

        _STATUS_NOTE = {
            "excluded": "❌ Excluded by stakeholder — confirm scope before ruling out",
            "partial":  "🔶 Partially elicited — further decomposition required",
            "unprobed": "⬜ Never elicited — architect review required",
        }

        if gate is not None and gate.seeded and gate.total > 0:
            for key, domain in gate.domains.items():
                if domain.status == "confirmed":
                    continue  # no stub needed

                status_note = _STATUS_NOTE.get(domain.status, "")
                req_count   = len(domain.req_ids)
                stub_id     = f"D-{key[:6].upper()}-01"

                lines.append(f"#### {domain.label}")
                lines.append(f"*Status: {status_note} | Requirements extracted so far: {req_count}*")
                lines.append("")
                lines.append(f"**[D] {stub_id}** — `[Architecture Review Required]`")
                lines.append(
                    f"*Expected requirement area:* {domain.label} — "
                    f"functional and non-functional requirements covering the full "
                    f"scope of this domain have not yet been elicited."
                )
                lines.append(
                    "*Action:* Conduct a focused follow-up elicitation session on "
                    f"'{domain.label}'. Identify: (1) what data the system must store, "
                    f"(2) what user actions are required, (3) what the system must do "
                    f"automatically, (4) what constraints or limits apply, and "
                    f"(5) what happens in error or edge-case scenarios."
                )
                lines.append("")
                stub_count += 1

            if stub_count == 0:
                lines.append(
                    "*All functional domains were confirmed or explicitly excluded. "
                    "No design-derived stubs required.*"
                )
                lines.append("")
        else:
            lines.append(
                "*Domain gate was not seeded during this session. "
                "No domain-specific stubs can be generated.*"
            )
            lines.append("")

        # ── D.2 IEEE-830 Structural Stubs ────────────────────────────────
        lines.append("### D.2 IEEE-830 Structural Stubs")
        lines.append("")
        lines.append(
            "*The following IEEE-830 sections had zero elicited content. "
            "A domain expert must confirm whether requirements belong here.*"
        )
        lines.append("")

        _SECTION_EXPECTED: dict[str, tuple[str, str]] = {
            "maintainability": (
                "§3.6.4 Maintainability",
                "Coding standards, documentation requirements, module independence, "
                "future-version compatibility.",
            ),
            "compatibility": (
                "§3.6.5 Portability / Compatibility",
                "Supported hardware standards, software platform constraints, "
                "technology restrictions.",
            ),
            "constraints": (
                "§3.5 Design Constraints",
                "Development methodology, required standards, mandated technology "
                "choices, document format requirements.",
            ),
        }

        structural_stub_count = 0
        for cat_key, (section_label, expected_content) in _SECTION_EXPECTED.items():
            if cat_key in state.covered_categories:
                continue
            stub_id = f"D-STR-{cat_key[:4].upper()}-01"
            lines.append(f"**[D] {stub_id}** — `[Architecture Review Required]`")
            lines.append(f"*IEEE-830 section:* {section_label}")
            lines.append(f"*Expected content:* {expected_content}")
            lines.append(
                "*Action:* Review with system architect and add formal requirements "
                "to the appropriate section before development begins.*"
            )
            lines.append("")
            structural_stub_count += 1

        if structural_stub_count == 0:
            lines.append("*All mandatory structural sections were covered.*")
            lines.append("")

        # ── D.3 Summary ──────────────────────────────────────────────────
        lines.append("### D.3 Design-Derived Stub Summary")
        lines.append("")
        lines.append("| Category | Count | Action Priority |")
        lines.append("|----------|-------|-----------------|")

        if gate is not None and gate.seeded:
            unprobed_count = sum(1 for d in gate.domains.values() if d.status == "unprobed")
            partial_count  = sum(1 for d in gate.domains.values() if d.status == "partial")
            excluded_count = sum(1 for d in gate.domains.values() if d.status == "excluded")
        else:
            unprobed_count = partial_count = excluded_count = 0

        lines.append(f"| Unprobed functional domains | {unprobed_count} | 🔴 Critical |")
        lines.append(f"| Partially elicited domains  | {partial_count}  | 🟡 High |")
        lines.append(f"| Excluded domains (confirm)  | {excluded_count} | 🟢 Low |")
        lines.append(f"| Structural IEEE-830 stubs   | {structural_stub_count} | 🟡 High |")
        lines.append(
            f"| **Total design-derived stubs** | **{stub_count + structural_stub_count}** | — |"
        )
        lines.append("")
        if stub_count + structural_stub_count > 0:
            lines.append(
                "> ℹ️ These stubs represent the lower-bound completeness gap. "
                "Running a targeted follow-up elicitation session is strongly "
                "recommended before finalising this SRS."
            )
            lines.append("")


# ---------------------------------------------------------------------------
# Convenience function (replaces the old generate_srs in conversation_manager)
# ---------------------------------------------------------------------------

def generate_srs_document(
    template: SRSTemplate,
    state: ConversationState,
    output_dir: Path,
    show_smart: bool = True,
) -> Path:
    """
    Top-level function called by ConversationManager at session end.

    Wraps SRSFormatter.write() with sensible defaults.
    This is the replacement for the old generate_srs() stub.
    """
    formatter = SRSFormatter(show_smart=show_smart)
    return formatter.write(template, state, output_dir)