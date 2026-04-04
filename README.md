# LLM-Based Requirements Engineering Assistant — Iteration 6

**University of Hildesheim · DSR Project**

---

## Overview

Iteration 6 builds on the five root-cause fixes from Iteration 5 by addressing three new issues: **shallow NFR coverage** (a single requirement was enough to satisfy each of the six mandatory NFR categories, so the LLM could satisfy the gate with low-quality data), **incomplete IEEE-830 structural sections** (the SRS was offered before narrative sections such as §1.2 Scope or §2.3 User Classes had been explicitly elicited), and **Volere artefacts** (Volere-specific framing lingered in prompts and state even though the project standardised on IEEE 830-1998 exclusively).

| Issue                           | Iteration 5 Problem                                                                                                                                                                     | Iteration 6 Fix                                                                                                                                                                                                                                                                                  |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Shallow NFR Coverage**        | `MIN_NFR_PER_CATEGORY = 1` — one vague requirement cleared a mandatory NFR gate                                                                                                         | `IT6-NFR-DEPTH`: `MIN_NFR_PER_CATEGORY` raised to **2**. `mandatory_nfrs_covered` now requires at least 2 requirements per category. Phase 3 hard stop is tiered: first probe opens the topic, depth probe fires when count == 1 and demands specific measurable follow-up                       |
| **Missing Structural Sections** | SRS was offered immediately after NFRs were covered; narrative sections (scope, user classes, operating environment, etc.) were left empty or filled by the hallucination-risk enricher | `IT6-PHASE4`: A new **Phase 4** is inserted between NFR completion and the SRS offer. The assistant must elicit 8 IEEE-830 narrative sections in order before `is_ready_for_srs()` returns `True`. Answers are captured with `<SECTION id="X.Y">` tags and stored in `state.srs_section_content` |
| **Volere References**           | Volere template labels ("Fit Criterion", "Customer", "Stakeholder") appeared in prompts and reports                                                                                     | `IT6-VOLERE`: All Volere references removed from `prompt_architect.py`, `conversation_state.py`, and `gap_detector.py`. IEEE-830 section numbering and terminology used exclusively throughout                                                                                                   |

The system continues to run as a **Flask web application** with a single-page HTML/JS UI.

---

## What's New in Iteration 6

### IT6-NFR-DEPTH — Raised NFR Depth Threshold (`prompt_architect.py`, `conversation_state.py`)

`MIN_NFR_PER_CATEGORY` is now **2** (previously 1). Every mandatory NFR category must have at least two distinct requirements before the NFR gate clears.

`ConversationState.mandatory_nfrs_covered` enforces this:

```python
@property
def mandatory_nfrs_covered(self):
    from domain_discovery import NFR_CATEGORIES
    from prompt_architect import MIN_NFR_PER_CATEGORY
    return all(self.nfr_coverage.get(c, 0) >= MIN_NFR_PER_CATEGORY for c in NFR_CATEGORIES)
```

`_build_context_block()` in `prompt_architect.py` uses a two-tier hard stop for NFRs. When a category has zero coverage, the standard opening probe is issued. When a category has exactly one requirement (below the new threshold of 2), a dedicated depth probe fires:

```
⛔ HARD STOP — NFR DEPTH REQUIRED: Performance Requirements [1/2]
You have 1 requirement(s) but need 2.
Ask for a MEASURABLE follow-up: "..."
Do NOT accept vague answers. Push for specific numbers/ranges.
```

The NFR panel in the context block is updated to show `(count/MIN_NFR_PER_CATEGORY)` per category with a `🔶` partial icon when coverage is non-zero but below threshold.

### IT6-PHASE4 — Structured IEEE-830 Documentation Phase (`prompt_architect.py`, `conversation_state.py`, `requirement_extractor.py`)

After all six NFR categories reach depth ≥ 2, a new Phase 4 begins. Eight IEEE-830 narrative sections are elicited one by one in a fixed order before the SRS is offered:

| Section ID | Label                            | Follow-up Allowed |
| ---------- | -------------------------------- | ----------------- |
| §1.2       | Scope                            | No                |
| §2.3       | User Classes and Characteristics | Yes               |
| §2.4       | Operating Environment            | Yes               |
| §2.5       | Assumptions and Dependencies     | Yes               |
| §3.1.1     | User Interfaces                  | Yes               |
| §3.1.3     | Software Interfaces              | Yes               |
| §3.1.4     | Communications Interfaces        | Yes               |
| §2.1       | Product Perspective              | No                |

The assistant transitions into Phase 4 with a one-time message: _"Great, I have all the requirements I need! I just have a few quick documentation questions to make sure the specification is complete."_

For each section the assistant asks the configured plain-language probe. If `can_ask_followup=True`, one clarifying question is allowed before the section is synthesised. Once the answer is captured, the assistant emits:

```
<SECTION id="2.3">
  IEEE-830 formal prose synthesised from the stakeholder's answer.
</SECTION>
```

`RequirementExtractor.extract_sections()` parses these tags using `_PATTERN_SECTION_TAG` and `commit_sections()` stores content into `state.srs_section_content` and marks the section as covered in `state.phase4_sections_covered`.

`ConversationState.is_ready_for_srs()` now requires Phase 4 to be fully complete:

```python
def is_ready_for_srs(self):
    if self.functional_count < MIN_FUNCTIONAL_REQS: return False
    if not self.mandatory_nfrs_covered: return False
    if self.domain_gate and self.domain_gate.seeded:
        if not self.domain_gate.is_satisfied: return False
    if len(self.phase4_sections_covered) < len(PHASE4_SECTIONS): return False
    return True
```

The `srs_ready` flag in `/api/session/turn` is also updated to account for Phase 4 progress, preventing premature display of the "Generate SRS" button.

The context block shows a Phase 4 progress panel on every turn:

```
PHASE 4 SECTIONS (3/8):
  ✅ §1.2 Scope
  ✅ §2.3 User Classes and Characteristics
  ✅ §2.4 Operating Environment
  ⬜ §2.5 Assumptions and Dependencies
  ⬜ §3.1.1 User Interfaces
  ...
```

### IT6-VOLERE — IEEE-830 Only (`prompt_architect.py`, `conversation_state.py`, `gap_detector.py`)

All references to Volere template fields ("Fit Criterion", "Customer Satisfaction", "Stakeholder") have been removed. The project now uses exclusively IEEE 830-1998 terminology and section numbering throughout all prompts, state structures, coverage reports, and generated SRS documents.

---

## Four-Phase Elicitation Flow

The elicitation session now follows four sequential phases, each gated by a `⛔ HARD STOP` directive:

| Phase                          | Trigger               | Gate Condition                                            |
| ------------------------------ | --------------------- | --------------------------------------------------------- |
| **Phase 1 — Domain Discovery** | Session start, turn 1 | Domain gate seeded; all domains `confirmed` or `excluded` |
| **Phase 2 — Functional Depth** | Domain gate satisfied | `functional_count >= MIN_FUNCTIONAL_REQS (10)`            |
| **Phase 3 — NFR Coverage**     | FR threshold met      | All 6 NFR categories have `nfr_coverage >= 2` (IT6)       |
| **Phase 4 — Documentation**    | NFRs at depth         | All 8 `PHASE4_SECTIONS` covered with `<SECTION>` tags     |
| **SRS Offer**                  | Phase 4 complete      | `is_ready_for_srs()` returns `True`                       |

A `✅ ALL GATES SATISFIED` message replaces the hard stop only when all four phases are complete.

---

## Architecture

```
app.py                              ← Flask REST API + HTML/JS UI
src/components/
├── conversation_manager.py         ← Session orchestration, LLM providers, turn loop
│                                     FIX-LOOP, FIX-MATCH, FIX-DEDUP, FIX-CAP
├── conversation_state.py           ← Session state, requirement store, coverage tracking
│                                     IT6-NFR-DEPTH (MIN=2), IT6-PHASE4 (srs_section_content,
│                                     phase4_sections_covered), IT6-VOLERE (IEEE-830 only)
├── domain_discovery.py             ← Dynamic domain gate: seed, reseed, probe, match, decompose
│                                     FIX-SEED, FIX-MATCH, FIX-2 (plain probes), FIX-3 (dedup context)
├── prompt_architect.py             ← 4-block dynamic prompt + 4-phase structure
│                                     IT6-NFR-DEPTH (tiered depth probes), IT6-PHASE4 (PHASE4_SECTIONS,
│                                     <SECTION> tag rules), IT6-VOLERE (IEEE-830 labels only)
├── srs_coverage.py                 ← IEEE-830 section completion with hallucination risk tiers
├── gap_detector.py                 ← IEEE-830 checklist + domain gate gap injection
│                                     IT6-VOLERE (Volere references removed)
├── question_generator.py           ← Domain-first proactive question generation
├── requirement_extractor.py        ← Multi-strategy requirement extraction from responses
│                                     IT6-PHASE4 (extract_sections, commit_sections)
├── srs_template.py                 ← IEEE-830 data model, progressively populated
└── srs_formatter.py                ← Renders SRSTemplate to Markdown / plain text / JSON
output/                             ← Generated SRS documents (.md)
logs/                               ← JSON session logs (per-session, per-turn gap reports)
```

### System Prompt Structure (Iteration 6)

`PromptArchitect.build_system_message()` assembles four ordered blocks each turn:

```
=== ROLE ===
  ROLE_BLOCK — identity, communication style, jargon ban
               Phase 4 constraint: session cannot close until Phase 4 complete

=== CURRENT SESSION CONTEXT ===
  _build_context_block() output:
  - Turn count, FR/NFR counts
  - ⛔ HARD STOP / ✅ directive (domain gate | NFR gap | NFR depth gap | Phase 4 section)
  - Domain gate table with status icons
  - NFR coverage checklist (count/MIN_NFR_PER_CATEGORY per category, 🔶 partial icon)
  - Phase 4 section progress checklist (IT6)
  - IEEE-830 structural coverage percentage

=== GAP DETECTION DIRECTIVE ===         (injected only when gap detector fires)
  ProactiveQuestionGenerator output

=== TASK INSTRUCTIONS ===
  TASK_BLOCK — Phase 1→2→3→4 structure, rules, <SECTION> tag format (IT6)
```

---

## Installation & Running

**Dependencies:**

```bash
pip install flask flask-cors openai requests
```

**Start the server:**

```bash
# OpenAI (default, recommended for evaluation)
OPENAI_API_KEY=sk-... python app.py --provider openai --model gpt-4o

# Ollama (university server)
OLLAMA_API_KEY=... python app.py --provider ollama --model llama3.1:8b

# Stub provider (UI testing, no API key required)
python app.py --provider stub
```

Navigate to `http://127.0.0.1:5000` in a browser.

**Options:**

| Flag         | Default     | Description                             |
| ------------ | ----------- | --------------------------------------- |
| `--provider` | `openai`    | LLM backend: `openai`, `ollama`, `stub` |
| `--model`    | `gpt-4o`    | Model name passed to the provider       |
| `--host`     | `127.0.0.1` | Bind address                            |
| `--port`     | `5000`      | Port number                             |
| `--debug`    | off         | Flask debug mode                        |

---

## REST API

| Method | Endpoint                    | Description                                               |
| ------ | --------------------------- | --------------------------------------------------------- |
| `POST` | `/api/session/start`        | Start a new elicitation session                           |
| `POST` | `/api/session/turn`         | Send a user message; receive assistant reply + gap report |
| `GET`  | `/api/session/status`       | Current coverage + gap report                             |
| `POST` | `/api/session/generate_srs` | Finalise session and generate SRS                         |
| `GET`  | `/api/session/download_srs` | Download the generated SRS file                           |
| `GET`  | `/api/health`               | Health check                                              |

The `/api/session/turn` response now includes `phase4_progress` and `phase4_sections_covered` within the `coverage_report` payload.

---

## Ablation Study

The ablation study flag from previous iterations is retained:

```bash
# Gap detection ON (default)
python app.py --provider ollama

# Gap detection OFF — pass in /api/session/start body
curl -X POST http://localhost:5000/api/session/start \
     -H "Content-Type: application/json" \
     -d '{"gap_detection": false}'
```

When `gap_detection=false`, `GapDetector` returns a fully-covered dummy report, no proactive questions are generated, and no directive is injected into the prompt. All other behaviour — domain gate, NFR phase (with depth), Phase 4 — is unaffected.

---

## Output Files

### SRS Document (`output/srs_<session_id>.md`)

A full IEEE 830-1998 compliant specification including:

- §1 Introduction (purpose, scope, definitions, overview)
- §2 Overall Description (product perspective, functions, user characteristics, constraints, assumptions) — now populated from Phase 4 `<SECTION>` tags before finalisation, with `srs_coverage.py` filling any remaining gaps
- §3 Specific Requirements (functional, interface, performance, reliability, security, maintainability, compatibility, usability)
- Appendix A: Traceability Matrix (req_id → section → source turn → SMART score)
- Appendix B: Coverage & Quality Report (domain completeness score, NFR depth coverage, Phase 4 section fill status)
- Appendix C: Conversation Transcript Summary

`srs_coverage.py` fills only sections not already populated by Phase 4. HIGH-risk sections (Hardware Interfaces, Logical Database Requirements, Design Constraints) contain formal stubs with architect checklists. MEDIUM-risk inferred sentences are marked `[inferred]`.

### Session Log (`logs/session_<session_id>.json`)

Structured JSON log with per-turn gap reports, domain gate status, NFR depth counters, Phase 4 section fill events, and a `srs_coverage_fill` event at finalisation.

---

## LLM Providers

| Provider | Class            | Env Var          | Notes                                           |
| -------- | ---------------- | ---------------- | ----------------------------------------------- |
| `openai` | `OpenAIProvider` | `OPENAI_API_KEY` | GPT-4o by default                               |
| `ollama` | `OllamaProvider` | `OLLAMA_API_KEY` | Hildesheim server; `OLLAMA_BASE_URL` optional   |
| `stub`   | `StubProvider`   | —                | Deterministic scripted responses for UI testing |

Temperature is fixed at `0.0` for the main conversation loop and all classification calls. Domain probe generation uses `temperature=0.3`. Decomposition uses `temperature=0.2`.

---

## Troubleshooting

**NFR gate does not clear after giving one answer per category**
This is expected behaviour in Iteration 6. `MIN_NFR_PER_CATEGORY` is now 2. The `🔶` icon in the coverage panel indicates a category has some coverage but is below threshold. The depth probe will ask for a specific measurable follow-up.

**Phase 4 questions appear after I said "I think that covers it"**
This is correct. The `ROLE_BLOCK` instructs the assistant not to agree with session-closing phrases while a `⛔ HARD STOP` is active. Phase 4 must complete all 8 sections before the SRS offer is made.

**`srs_ready` stays `false` after all NFRs appear green**
Check the Phase 4 section progress panel. `is_ready_for_srs()` now also requires `len(phase4_sections_covered) >= len(PHASE4_SECTIONS)`. The panel shows which sections are still `⬜`.

**`<SECTION>` tags missing from assistant responses**
The LLM did not emit the tag after the Phase 4 answer. This can happen if the answer was very short and the follow-up path was taken. Verify that `prompt_architect.py` is Iteration 6 (check for the `<SECTION id="...">` format rule in `TASK_BLOCK`) and that the provider is reachable.

**Conversation keeps asking the same question**
See Iteration 5 `FIX-LOOP`. If it recurs, confirm `conversation_manager.py` is Iteration 5+ and restart the server.

**Probe questions contain technical jargon**
See Iteration 5 `FIX-JARGON`. Ensure `domain_discovery.py` is current and the provider is reachable (probe generation falls back to a template string on API failure).

**SRS §2.x sections are empty despite Phase 4 completing**
`srs_coverage.py` acts as a fallback for sections not covered by Phase 4 tags. If both Phase 4 content and `srs_coverage.py` are missing, verify the provider is reachable at finalisation and that `srs_coverage.py` exists in `src/components/`.

**Ollama connection error**
Verify `OLLAMA_API_KEY` is set and the university VPN is active if required.

**OpenAI authentication error**
Verify `OPENAI_API_KEY` is set and has sufficient quota.

**Port already in use**

```bash
python app.py --port 5001
```

---

## Research Foundation

Iteration 6 addresses three failure modes identified in the Iteration-5 post-mortem:

- **`IT6-NFR-DEPTH`** closes a gating loophole where one vague requirement was sufficient to satisfy a mandatory NFR category. Raising `MIN_NFR_PER_CATEGORY` to 2 and adding a depth probe forces the assistant to elicit at least one measurable follow-up per category.
- **`IT6-PHASE4`** addresses the persistent gap between high domain/NFR coverage scores and low SRS structural completeness. By making Phase 4 a hard gate before the SRS offer, all eight narrative IEEE-830 sections are explicitly elicited from the stakeholder rather than inferred or left empty.
- **`IT6-VOLERE`** removes conceptual ambiguity introduced by mixing two incompatible standards. All artefacts now use IEEE 830-1998 exclusively, ensuring consistent section numbering and terminology across prompts, state, and output documents.

---

## License

Academic Research Project — University of Hildesheim

Team members: Hunain Murtaza (1750471) · David Tashjian (1750243) · Saad Younas (1750124) · Amine Rafai (1749821) · Khaled Shaban (1750283) · Mohammad Alsaiad (1750755)
