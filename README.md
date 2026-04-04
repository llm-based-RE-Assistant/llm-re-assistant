# RE Assistant — Iteration 4

**Requirements Engineering Assistant | University of Hildesheim**

An AI-powered elicitation tool that conducts structured requirements interviews, detects coverage gaps in real time, and generates IEEE 830-compliant Software Requirements Specifications (SRS).

---

## Table of Contents

- [Overview](#overview)
- [What's New in Iteration 4](#whats-new-in-iteration-4)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Running the Application](#running-the-application)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Component Reference](#component-reference)
- [SRS Output Format](#srs-output-format)
- [Ablation Study Support](#ablation-study-support)
- [Configuration](#configuration)
- [Known Limitations](#known-limitations)

---

## Overview

The RE Assistant automates the requirements elicitation process through a conversational interview. It proactively identifies missing requirements using an IEEE 830 coverage checklist, generates targeted follow-up questions to fill gaps, and produces a structured SRS document at the end of the session.

**Key capabilities:**

- Conversational elicitation guided by a structured, phase-aware prompt architect
- Dynamic domain gate: LLM seeds functional domains from the first user message and tracks coverage per domain
- Real-time gap detection across 18 IEEE 830 coverage categories
- Proactive follow-up question generation (LLM-powered or template fallback)
- Automatic requirement extraction and classification from LLM responses using `<REQ>` tags
- NFR depth enforcement: each of 6 mandatory NFR categories requires ≥ 2 measurable requirements
- Phase 4 documentation: after all requirements are elicited, the assistant completes 8 IEEE 830 narrative sections interactively using `<SECTION>` tags
- SRS Coverage Enricher: fills any remaining empty IEEE 830 sections via LLM synthesis or architect-review stubs
- SMART quality annotation for every extracted requirement
- Full IEEE 830-1998 SRS document generation in Markdown with dual coverage metrics
- Single-page web UI with live domain gate ring, IEEE-830 ring, gap panel, and follow-up question panel
- Ablation study support: gap detection can be toggled on/off per session

---

## What's New in Iteration 4

| Feature                              | Description                                                                                                                                                                                                                                             |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Dynamic Domain Gate**              | LLM seeds 8–12 functional domains from the stakeholder's first message. Each domain is tracked through `unprobed → partial → confirmed` states. The gate must be fully satisfied before NFR elicitation begins                                          |
| **Domain Re-seeding**                | At turn 4 and turn 8, the domain list is automatically extended with any functional domains implied by requirements captured so far but not yet in the gate                                                                                             |
| **Requirement Decomposition**        | For every confirmed domain with ≥ 2 requirements, the LLM generates 2–5 missing atomic requirements covering data, actions, constraints, automation, and edge cases                                                                                     |
| **LLM Domain Matching**              | Each extracted requirement is matched to a domain key via an LLM call instead of rule-based heuristics, removing false mismatches                                                                                                                       |
| **NFR Depth Enforcement (Phase 3)**  | Each of 6 mandatory NFR categories (`performance`, `usability`, `security_privacy`, `reliability`, `compatibility`, `maintainability`) now requires ≥ 2 measurable requirements. The assistant issues a targeted depth probe if only 1 exists           |
| **Phase 4 — IEEE 830 Documentation** | After all NFRs reach depth, the assistant asks 8 structured questions to populate narrative SRS sections (scope, user classes, operating environment, assumptions, interfaces, product perspective). Answers are captured via `<SECTION id="X.Y">` tags |
| **SRS Coverage Enricher**            | `srs_coverage.py` fills empty IEEE 830 sections at session end: Phase 4 customer answers take priority; LLM synthesis fills the rest; high-risk sections (hardware interfaces, database, design constraints) always get architect-review stubs          |
| **Sub-dimension Tagging**            | Each requirement is classified into one of five sub-dimensions (`data`, `actions`, `constraints`, `automation`, `edge_cases`) for richer domain coverage reporting                                                                                      |
| **Dual Metric UI**                   | The left panel now shows two separate coverage rings: domain gate completeness (%) and IEEE 830 structural coverage (%), each with colour-coded thresholds                                                                                              |
| **Domain Gate UI List**              | The left panel now has a Domains / IEEE-830 tab switcher. The Domains tab shows each domain with its status icon and dynamic labels from the server                                                                                                     |
| **Duplicate Detection**              | Turn-level Jaccard similarity check prevents duplicate user messages from advancing the conversation with repeated probes                                                                                                                               |
| **Decomposition Deduplication**      | Decomposed requirements are compared against existing ones using similarity scoring; near-duplicates are silently dropped                                                                                                                               |

---

## Architecture

```
Browser  ──POST/GET──►  Flask REST API (app.py)
                               │
                    ConversationManager
                    ┌──────────┼──────────┐
                    │          │          │
             PromptArchitect  │   RequirementExtractor
                    │         │          │
               LLMProvider    │    ConversationState
          (OpenAI/Ollama/Stub) │          │
                    │         │     SRSTemplate
                    │         │          │
             DomainDiscovery  │    SRSFormatter
             (seed/reseed/    │
              match/decompose)│
                    │         │
             GapDetector      │
                    │         │
        ProactiveQuestionGenerator
                              │
                    SRSCoverageEnricher
```

**Request flow per turn:**

1. `PromptArchitect` builds a system message with live session context (phase, gate status, NFR depth, Phase 4 progress) and any gap directive from the previous turn
2. The LLM produces a response
3. `RequirementExtractor` parses `<REQ>` tags and, in Phase 4, `<SECTION>` tags from the response
4. `DomainDiscovery` LLM-matches each requirement to a domain, classifies NFR category and sub-dimension, and decomposes confirmed domains
5. Domain gate re-seeding runs at turns 4 and 8
6. `SRSTemplate.update_from_requirements()` syncs the template
7. `GapDetector.analyse()` produces a `GapReport`
8. `ProactiveQuestionGenerator.generate()` produces a `QuestionSet`
9. The gap directive is injected into `PromptArchitect.extra_context` for the next turn
10. The API returns the assistant reply, gap report, follow-up questions, and dual coverage metrics to the UI

**At session end:**

1. `SRSCoverageEnricher.enrich()` fills remaining empty sections (Phase 4 answers → LLM synthesis → stubs)
2. `SRSFormatter.write()` renders the full IEEE 830 Markdown document

---

## Project Structure

```
.
├── app.py                    # Flask REST API and entry point
├── index.html                # Single-page web UI
├── conversation_manager.py   # Orchestrates the full elicitation session
├── conversation_state.py     # Session state, requirement store, coverage tracking
├── prompt_architect.py       # System message builder; phase definitions; IEEE 830 registry
├── domain_discovery.py       # Domain gate seeding, matching, decomposition, NFR classification
├── gap_detector.py           # Coverage checklist and gap analysis
├── question_generator.py     # Proactive follow-up question generation
├── requirement_extractor.py  # Extracts <REQ> and <SECTION> tags from LLM responses
├── srs_template.py           # IEEE 830 SRS data model (progressively populated)
├── srs_formatter.py          # Renders SRSTemplate to Markdown
├── srs_coverage.py           # Fills empty SRS sections (Phase 4 / LLM synthesis / stubs)
├── logs/                     # Session JSON logs (auto-created)
└── output/                   # Generated SRS documents (auto-created)
```

---

## Installation

**Requirements:** Python 3.10+

```bash
# 1. Clone the repository
git clone <repo-url>
cd re-assistant

# 2. Install Python dependencies
pip install flask flask-cors requests

# 3. For OpenAI provider
pip install openai

# 4. Set your API key (if using OpenAI or Ollama)
export OPENAI_API_KEY=sk-...
# or
export OLLAMA_API_KEY=<your-key>
export OLLAMA_BASE_URL=https://your-ollama-host/ollama   # optional, has default
```

---

## Running the Application

```bash
# Default: OpenAI GPT-4o
python app.py

# Specify a different model
python app.py --provider openai --model gpt-4o-mini

# Local Ollama
python app.py --provider ollama --model llama3.1:8b

# Stub provider (no API key needed — for testing)
python app.py --provider stub

# Custom host / port
python app.py --host 0.0.0.0 --port 8080 --debug
```

Then open **http://127.0.0.1:5000** in your browser.

### CLI options

| Flag         | Default     | Description                              |
| ------------ | ----------- | ---------------------------------------- |
| `--provider` | `openai`    | LLM provider: `openai`, `ollama`, `stub` |
| `--model`    | `gpt-4o`    | Model name (passed to the provider)      |
| `--host`     | `127.0.0.1` | Bind address                             |
| `--port`     | `5000`      | Port                                     |
| `--debug`    | off         | Enable Flask debug mode                  |

---

## Usage

1. Open the web UI and optionally toggle **Gap Detection** on or off.
2. Click **Start Elicitation Session**.
3. Describe the software system you want to build — its purpose, users, and key features.
4. Respond to the assistant's questions. Each response updates:
   - The **Domain ring** (left panel, primary) — percentage of functional domains confirmed or excluded
   - The **IEEE-830 ring** (left panel, secondary) — percentage of structural categories covered
   - The **Domains / IEEE-830 tab** (left panel) — per-domain or per-category status list
   - The **Gaps panel** (right panel) — uncovered categories ranked by severity
   - The **Follow-ups panel** (right panel) — one proactive question targeting the highest-priority gap
5. The assistant automatically progresses through four phases:
   - **Phase 1 (turns 1–2):** Listen, build context, seed domain gate
   - **Phase 2 (turns 3+):** Probe each functional domain until the gate is satisfied
   - **Phase 3:** Collect ≥ 2 measurable requirements for each of 6 mandatory NFR categories
   - **Phase 4:** Complete 8 IEEE 830 narrative documentation sections interactively
6. Once all gates are satisfied, the **Generate SRS** button becomes available. Click it to produce the document.
7. Click **Download** in the success banner to save the Markdown SRS file.

### Requirement tagging

The assistant wraps formalised requirements in XML tags that are automatically extracted:

```xml
<REQ type="functional" category="temperature_control">
The system shall allow users to set a target temperature between 10°C and 30°C for each zone.
</REQ>
```

Supported types: `functional`, `non_functional`, `constraint`

Supported categories: `functional`, `performance`, `usability`, `security_privacy`, `reliability`, `compatibility`, `maintainability`, `interfaces`, `constraints`, `stakeholders`, `scope`, `purpose`

### Section tagging (Phase 4)

During Phase 4, the assistant emits IEEE 830 narrative sections:

```xml
<SECTION id="2.3">
The system shall serve two primary user classes. Regular Users interact with the
mobile application to monitor and control household devices. The Administrator
configures system-wide settings and manages user accounts. It is assumed that
regular users have basic smartphone proficiency; no technical expertise is required.
</SECTION>
```

Supported section IDs: `1.2`, `2.1`, `2.3`, `2.4`, `2.5`, `3.1.1`, `3.1.3`, `3.1.4`

---

## API Reference

All endpoints accept and return JSON.

### `POST /api/session/start`

Start a new elicitation session.

**Request body:**

```json
{ "gap_detection": true }
```

**Response:**

```json
{
  "session_id": "a1b2c3d4",
  "opening_message": "Hello! I'm your Requirements Engineering assistant...",
  "gap_detection": true,
  "provider": "openai"
}
```

---

### `POST /api/session/turn`

Send one user message and receive the assistant reply.

**Request body:**

```json
{
  "session_id": "a1b2c3d4",
  "message": "I want to build a smart home automation app..."
}
```

**Response:**

```json
{
  "session_id": "a1b2c3d4",
  "assistant_reply": "...",
  "turn_id": 5,
  "gap_report": {
    "coverage_pct": 57.1,
    "critical_gaps": [...],
    "important_gaps": [...],
    "optional_gaps": [...],
    "all_categories": { "purpose": "covered", "performance": "partial", ... }
  },
  "follow_up_questions": [
    {
      "question_id": "domain_temperature_control_1",
      "category_key": "domain_temperature_control",
      "category_label": "Temperature Control",
      "question_text": "If the internet goes out, should the thermostat keep the last scheduled temperature or let users override it manually?",
      "severity": "critical",
      "source": "domain_gate"
    }
  ],
  "coverage_report": {
    "domain_gate_status": { "temperature_control": "confirmed", "lighting_control": "partial", ... },
    "domain_gate_labels": { "temperature_control": "Temperature Control", ... },
    "domain_completeness_pct": 62,
    "phase4_progress": "3/8",
    ...
  },
  "srs_ready": false
}
```

---

### `GET /api/session/status`

Get the current coverage and gap report without sending a message.

**Query params:** `session_id=a1b2c3d4`

---

### `POST /api/session/generate_srs`

Generate the SRS document for the session. Requires at least 5 functional requirements.

**Request body:**

```json
{ "session_id": "a1b2c3d4" }
```

**Response:**

```json
{
  "session_id": "a1b2c3d4",
  "srs_path": "output/SRS_a1b2c3d4_20240915_143022.md",
  "success": true
}
```

---

### `GET /api/session/download_srs`

Download the generated SRS file.

**Query params:** `session_id=a1b2c3d4`

Returns the Markdown file as a download attachment.

---

### `GET /api/health`

```json
{ "status": "ok", "provider": "openai" }
```

---

## Component Reference

### `DomainDiscovery`

The central new component of Iteration 4. Manages the functional domain gate through the session lifecycle.

**Seeding (`seed()`):** On turn 1, an LLM prompt identifies 8–12 functional domains from the stakeholder's first message. For every physical device or sensor mentioned, the prompt forces a corresponding control domain (e.g., thermostat → Temperature Control).

**Re-seeding (`reseed()`):** At turns 4 and 8, a second LLM prompt inspects requirements captured so far and adds any missing domains not in the original seed.

**LLM domain matching (`match_requirement_to_domain()`):** Each extracted requirement is matched to its domain via an LLM call against the full domain key list. Falls back to partial key matching.

**NFR classification (`classify_nfr()`):** Classifies each non-functional requirement into one of 6 mandatory categories (`performance`, `usability`, `security_privacy`, `reliability`, `compatibility`, `maintainability`).

**Sub-dimension classification (`classify_subdimension()`):** Tags each requirement as one of `data`, `actions`, `constraints`, `automation`, or `edge_cases` for intra-domain coverage depth.

**Decomposition (`decompose_requirements()`):** For confirmed domains with ≥ 2 requirements, generates 2–5 missing atomic requirements using a prompt that sees both domain-specific and all-other requirements as context.

**Domain status transitions:**

- `unprobed` → `partial` (≥ 1 requirement matched)
- `partial` → `confirmed` (≥ 3 requirements matched)
- `excluded` (set directly if stakeholder rules out a domain)

---

### `PromptArchitect`

Builds a four-block system message on every turn. The context block (`_build_context_block`) now contains a phase-aware `⛔ HARD STOP` or `✅ ALL GATES SATISFIED` directive:

| Phase                  | Trigger                       | Hard Stop Content                                           |
| ---------------------- | ----------------------------- | ----------------------------------------------------------- |
| Gate unseeded          | Turn 1                        | Prompt to listen and build context                          |
| Domain gate incomplete | Gate not satisfied            | Next unprobed/partial domain + pre-generated probe question |
| NFR Phase 3            | Gate satisfied, NFR count < 2 | Category with lowest count; depth probe if count = 1        |
| Phase 4                | All NFRs at depth             | Next uncovered IEEE 830 section + probe question            |
| All complete           | All gates met                 | Offer SRS generation                                        |

The `PHASE4_SECTIONS` list defines 8 ordered sections, each with a section ID, label, probe question, and a `can_ask_followup` flag.

---

### `GapDetector`

Analyses a `ConversationState` and returns a `GapReport`. Covers 18 categories drawn from IEEE 830.

**In Iteration 4**, NFR categories use the `nfr_coverage` counter against `MIN_NFR_PER_CATEGORY = 2` (raised from 1). A category with count 1 is `partial`; count ≥ 2 is `covered`.

**Domain gate gap injection:** After standard analysis, any `unprobed` or `partial` domain is injected as a synthetic critical gap with its pre-generated probe question as the description, visually separated in the UI.

---

### `RequirementExtractor`

Parses `<REQ type="..." category="..."> ... </REQ>` tags from LLM responses. Falls back to numbered "Requirement N (Type):" patterns, then to bare "The system shall ..." sentences. Deduplicates by normalised text before committing to state.

**New in Iteration 4:** `extract_sections()` and `commit_sections()` parse `<SECTION id="X.Y"> ... </SECTION>` tags from Phase 4 responses and store them in `state.srs_section_content` and `state.phase4_sections_covered`.

---

### `SRSCoverageEnricher`

New in Iteration 4. Fills empty IEEE 830 SRS sections before document rendering using a consumer-first strategy:

1. **Phase 4 content (highest priority):** If the customer answered a section during Phase 4, their answer is used verbatim.
2. **LLM synthesis (low-risk sections):** Scope, product perspective, product functions, user classes, assumptions, operating environment, user documentation, and interface sections are synthesised from elicited requirements using targeted prompts.
3. **Architect-review stubs (high-risk sections):** Hardware interfaces, logical database requirements, and design constraints always receive clearly marked stubs with an architect checklist rather than LLM fabrication.

`render_section2_extras()` and `render_section35_stub()` are helper functions called by `SRSFormatter` to emit sentinel-prefixed content stored in `general_constraints` and `section1.references`.

---

### `SRSTemplate`

Progressive IEEE 830 data model. Updated after every turn via `update_from_requirements()`. Runs a heuristic SMART check on every new requirement:

| Dimension   | Heuristic                                            |
| ----------- | ---------------------------------------------------- |
| Specific    | Starts with a defined actor (system / user / admin)  |
| Measurable  | Contains a numeric value or unit                     |
| Testable    | Uses IEEE "shall" form                               |
| Unambiguous | Contains no vague adjectives (fast, simple, good, …) |
| Relevant    | Non-empty text (assumed true)                        |

---

### `SRSFormatter`

Renders an `SRSTemplate` to IEEE 830 Markdown. New in Iteration 4:

- **Dual metrics in header:** Domain Completeness Score and IEEE-830 Elicitation Coverage reported separately
- **Appendix D — Design-Derived Requirements Inventory:** Dynamic stubs for all unconfirmed domains and uncovered structural sections, replacing the hard-coded domain-specific lists from earlier iterations
- **Phase 4 section rendering:** `render_section2_extras()` emits §2.4 Operating Environment and §2.6 User Documentation; `render_section35_stub()` emits architect-review stubs for §3.5

---

## SRS Output Format

Generated documents are IEEE 830-1998 Markdown files saved to `output/`. Each document contains:

| Section                            | Content                                                                      |
| ---------------------------------- | ---------------------------------------------------------------------------- |
| Header                             | Project name, session metadata, dual coverage metrics, quality summary       |
| §1 Introduction                    | Purpose, scope (Phase 4 or LLM-synthesised), definitions, references         |
| §2.1 Product Perspective           | Phase 4 or LLM-synthesised                                                   |
| §2.2 Product Functions             | Per-domain LLM narrative summaries                                           |
| §2.3 User Characteristics          | Phase 4 or LLM-synthesised with Markdown table                               |
| §2.4 Operating Environment         | Phase 4 or LLM-synthesised                                                   |
| §2.5 Assumptions & Dependencies    | Phase 4 or LLM-synthesised numbered list                                     |
| §2.6 User Documentation            | LLM-synthesised from usability requirements                                  |
| §3.1 Functional Requirements       | Extracted FRs with SMART badges and priority labels                          |
| §3.2 External Interfaces           | Phase 4 or LLM-synthesised; hardware always stubbed                          |
| §3.3 Performance Requirements      | Extracted NFRs (performance category)                                        |
| §3.4 Logical Database Requirements | Architect-review stub with implied-data checklist                            |
| §3.5 Design Constraints            | Extracted CON requirements or architect-review stub                          |
| §3.6 System Attributes             | Reliability, availability, security, maintainability, portability, usability |
| Appendix A                         | Traceability matrix (all requirements × metadata)                            |
| Appendix B                         | Elicitation coverage and SMART quality report                                |
| Appendix C                         | Turn-by-turn conversation transcript summary                                 |
| Appendix D                         | Design-derived stubs for unconfirmed domains and uncovered IEEE 830 sections |

---

## Ablation Study Support

Gap detection can be disabled per session for controlled evaluation:

**Via the UI:** toggle the "Gap Detection" switch before starting a session.

**Via the API:**

```json
POST /api/session/start
{ "gap_detection": false }
```

**Programmatically:**

```python
manager = ConversationManager(provider=..., gap_enabled=False)
```

When disabled, `GapDetector` returns a full-coverage report (100%, no gaps) and `ProactiveQuestionGenerator` receives no gap targets.

---

## Configuration

| Environment Variable | Description                                                            |
| -------------------- | ---------------------------------------------------------------------- |
| `OPENAI_API_KEY`     | Required for the OpenAI provider                                       |
| `OLLAMA_API_KEY`     | Required for the Ollama provider                                       |
| `OLLAMA_BASE_URL`    | Ollama base URL (default: `https://genai-01.uni-hildesheim.de/ollama`) |

Key thresholds in `prompt_architect.py`:

| Constant               | Default | Description                                                                     |
| ---------------------- | ------- | ------------------------------------------------------------------------------- |
| `MIN_FUNCTIONAL_REQS`  | 10      | Minimum functional requirements before Phase 3 NFR probing begins               |
| `MIN_NFR_PER_CATEGORY` | 2       | Minimum measurable requirements per NFR category (raised from 1 in Iteration 4) |

Log files are written to `logs/session_<id>.json`. Generated SRS files are written to `output/SRS_<id>_<timestamp>.md`. Both directories are created automatically on first run.

---

## Known Limitations

- **Session persistence:** Sessions are stored in memory only. Restarting the server loses all active sessions.
- **LLM call volume:** Iteration 4 makes multiple LLM calls per turn (domain matching, NFR classification, sub-dimension classification, and optionally decomposition and probe question generation). High-latency providers may cause noticeable turn delays.
- **Domain gate seeding quality:** Seed accuracy depends on the first user message. Vague or very short opening messages may produce an incomplete or generic domain list. Re-seeding at turns 4 and 8 mitigates this.
- **SMART heuristics:** Quality scoring uses lightweight keyword heuristics, not full NLP. Measurability detection relies on numeric patterns and may miss domain-specific units.
- **Requirement extraction:** The extractor depends on the LLM consistently using `<REQ>` and `<SECTION>` tags. Malformed or missing tags cause fallback to weaker pattern matching.
- **SRS coverage stubs:** High-risk sections (hardware interfaces, database, design constraints) are always stubbed rather than LLM-synthesised. These require manual completion by a system architect before the SRS can be used for development.
- **Single-user:** No authentication or multi-user isolation. Not intended for production deployment.

---

_RE Assistant — Iteration 4 | University of Hildesheim_
