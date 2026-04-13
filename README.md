# RE Assistant — Iteration 5

**Requirements Engineering Assistant | University of Hildesheim**

An AI-powered elicitation tool that conducts structured stakeholder interviews, detects coverage gaps in real time, enforces IEEE 830-1998 completeness across functional domains and non-functional categories, and generates a full Software Requirements Specification (SRS) document.

---

## Table of Contents

- [Overview](#overview)
- [What's New in Iteration 5](#whats-new-in-iteration-5)
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

## Installation & Running

**Dependencies:**

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
# OpenAI (default, recommended for evaluation)
OPENAI_API_KEY=sk-... python app.py --provider openai --model gpt-4o

# Ollama (university server)
OLLAMA_API_KEY=... python app.py --provider ollama --model llama3.1:8b

# Local Ollama
python app.py --provider ollama --model llama3.1:8b

# Stub provider (no API key needed — for testing)
python app.py --provider stub
```

Navigate to `http://127.0.0.1:5000` in a browser.

**Options:**

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

**Request:** `{ "session_id": "a1b2c3d4" }`

**Response:** `{ "srs_path": "output/SRS_a1b2c3d4_1234567890.md", "download_url": "/api/session/download?session_id=a1b2c3d4" }`

---

#### `GET /api/session/download?session_id=<id>`

Download the generated SRS Markdown file.

---

### Logs

#### `GET /api/logs?project_id=<id>`

List session logs for a project. Returns metadata: session_id, turn_count, req_count, started_at, updated_at, is_active.

#### `GET /api/logs/<session_id>/replay`

Return conversation turns for a session (from live memory or disk). Includes domain gate snapshot and NFR coverage.

#### `GET /api/logs/<session_id>/download`

Download the raw JSON session log.

---

#### `GET /api/health`

Returns `{ "status": "ok", "provider": "openai", "version": "iteration-5" }`.

---

## Component Reference

### `ConversationManager`

Orchestrates the full session lifecycle. Key responsibilities:

- `start_session()` — creates session state, initialises DomainGate, and returns the session tuple
- `inject_requirements()` — injects preprocessed requirements into session state (used by the upload pipeline); tracks NFR coverage during injection
- `seed_domains_from_preprocessed()` — seeds domain gate directly from category labels found in uploaded requirements, bypassing the LLM seed call
- `send_turn()` — builds system prompt, calls LLM, extracts requirements and sections, runs SMART check, performs domain matching, NFR classification, sub-dimension tagging, decomposition, and domain status update
- `finalize_session()` — runs SRS coverage enrichment and generates the final document

**History window:** last 10 turns are included in each LLM call (`MAX_HISTORY_TURNS = 10`).

---

### `RequirementPreprocessor`

New in Iteration 5. Accepts a list of raw requirement strings and a project context string. Calls the LLM once to:

- Classify each requirement as `functional`, `non_functional`, or `constraint`
- Assign a category key and human-readable label
- Assign a SMART score (1–5)
- Rewrite vague requirements to be measurable
- Split compound requirements into atomic items

Returns a `PreprocessResult` with `ProcessedRequirement` objects carrying `final_text`, `req_type`, `category`, `category_label`, `smart_score`, `was_rewritten`, and `was_split`.

---

### `DomainDiscovery`

**Seeding (`seed()`):** Called on turn 1. The LLM infers 8–15 functional domain labels from the stakeholder's first message. Each label is converted to a `snake_case` key and stored as a `DomainSpec` in the gate.

**Seeding from labels (`seed_from_labels()`):** Seeds the domain gate directly from a known list of label strings without an LLM call. Used when domains are derived from an uploaded requirements file.

**Re-seeding (`reseed()`):** At turns 10, 20, and 30, inspects all requirements captured so far and adds any implied domains not yet in the gate. The requirement sample is drawn evenly across domain categories (up to 40 requirements) for better breadth. System complexity is included in the re-seed prompt.

**Domain matching (`match_requirement_to_domain()`):** Matches each extracted requirement to a domain key via LLM. Falls back to partial key string matching.

**NFR classification (`classify_nfr()`):** Maps non-functional requirements to one of 6 mandatory categories. First checks if the `<REQ category="...">` tag already contains a valid NFR key before calling the LLM.

**Sub-dimension classification (`classify_subdimension()`):** Tags each requirement as `data`, `actions`, `constraints`, `automation`, or `edge_cases`.

**Decomposition (`decompose_requirements()`):** For domains with ≥ 2 requirements, generates missing atomic requirements guided by the domain's coverage template checklist. The [NFR] prefix in generated text signals quality-attribute requirements stored as `NON_FUNCTIONAL`. Re-runs whenever the domain has grown by ≥ 3 requirements since the last pass (`decompose_count` tracks runs). Anti-duplication context includes up to 40 sampled requirements.

**Domain status transitions:**

| Transition | Condition |
|---|---|
| `unprobed` → `partial` | ≥ 1 requirement matched to domain |
| `partial` → `confirmed` | ≥ 3 requirements matched **AND** `probe_count >= 1` |
| any → `excluded` | Stakeholder marks domain out of scope |

---

### `DomainGate`

Central data structure tracking the state of functional domain coverage.

**`is_satisfied`** — the single source of truth for domain gate completion. Requires:
1. Gate has been seeded and has at least one domain.
2. At least 80 % of in-scope (non-excluded) domains are `confirmed`.
3. Every in-scope unconfirmed domain has `probe_count >= 1` (no domain silently skipped).

Used by both `determine_elicitation_phase()` and `ConversationState.is_ready_for_srs()`.

**`completeness_pct`** — `confirmed_count / active_count × 100`, where `active_count` excludes excluded domains.

---

### `PromptArchitect`

Builds a phase-specific system message on every turn.

**Phase 1 (FR):** Role block + `_build_domain_context()` — shows current domain, its requirement counts by type, a per-domain coverage checklist with `[COVERED] / [PENDING] / [OUT-OF-SCOPE]` cross-check instructions, and the remaining domain list.

**Phase 2 (NFR):** Role block + `_build_nfr_context()` — shows current NFR category, its coverage count vs threshold, probe hints, example requirements, and the status of all 6 categories.

**Phase 3 (IEEE):** Role block + `_build_ieee_section_context()` — shows the current uncovered IEEE 830 section, a suggested question, completed and remaining sections, and total requirement counts.

**SRS-only mode:** Uses `_build_srs_only_message()` — always in `ieee` phase, includes a compact requirements summary.

---

### `GapDetector`

Analyses `ConversationState` and returns a `GapReport` across 14 IEEE 830 categories. NFR categories use `state.nfr_coverage` counts against `MIN_NFR_PER_CATEGORY`. Structural categories use keyword matching against the full conversation corpus plus `state.covered_categories`.

**Domain gate gap injection:** After standard analysis, unprobed and partial domains are injected as synthetic critical gaps with their pre-generated probe question as the description.

**Coverage-hint injection:** `question_generator.py` selects the highest-priority gap and builds a `── COVERAGE HINT ──` block appended to the system prompt. The hint suggests a question verbatim but frames it as optional guidance rather than a command, preserving natural conversation flow.

---

### `RequirementExtractor`

Parses `<REQ type="..." category="..."> ... </REQ>` tags from LLM responses. Falls back to numbered `Requirement N (Type):` patterns, then to bare `The system shall ...` sentences. Deduplicates by normalised text before committing to state.

**Phase 3:** `extract_sections()` parses `<SECTION id="X.Y"> ... </SECTION>` tags. `commit_sections()` stores content in `state.srs_section_content` and marks sections as covered in `state.phase4_sections_covered`. Appends to existing content if a section is revisited across multiple turns.

---

### `SRSCoverageEnricher`

Fills empty IEEE 830 sections before document rendering using a three-tier strategy:

1. **Phase 3 customer answers (highest priority):** If the customer answered a section during Phase 3, their answer is used directly.
2. **LLM synthesis (low-risk sections):** Scope, product perspective, product functions, user classes, assumptions and dependencies, operating environment, user documentation, user/software/communication interfaces — all synthesised from elicited requirements using targeted prompts. Every inferred statement is marked `[INFERRED]`.
3. **Architect-review stubs (high-risk sections):** Hardware interfaces, logical database requirements, and design constraints always receive clearly marked stubs with an architect checklist. These are never LLM-fabricated.

The `§2.2 Product Functions` section is special: for each non-excluded domain in the gate, a dedicated LLM call synthesises a 2–4 sentence capability description from that domain's functional requirements alone.

---

### `SRSTemplate`

Progressive IEEE 830 data model updated after every turn via `update_from_requirements()`. Runs a heuristic SMART check on every new requirement: Specific (actor-subject present), Measurable (numeric pattern present), Testable (uses "shall"), Unambiguous (no vague adjectives), Relevant (non-empty). The LLM-based batch check in `ConversationManager` supersedes these heuristics and can rewrite requirement text.

---

### `SRSFormatter`

Renders `SRSTemplate` to full IEEE 830 Markdown. Key sections:

- **SMART quality badges** on every requirement (`★★★ 4/5`, per-dimension breakdown, rewrite notes)
- **Appendix A — Traceability Matrix:** all requirements × (type, category, section, turn, priority, SMART score, text)
- **Appendix B — Coverage & Quality Report:** session metrics table, domain gate breakdown, NFR coverage table, SMART dimension analysis, IEEE-830 category grid
- **Appendix C — Conversation Transcript Summary:** turn-by-turn user/assistant excerpts (truncated for readability)
- **Appendix D — Design-Derived Requirements Inventory:** domain-agnostic `[D]`-tagged stubs for all unconfirmed domains and uncovered structural sections; no hard-coded domain-specific content

---

## SRS Output Format

Generated documents are saved to `output/` as `SRS_<session_id>_<timestamp>.md`. Each document contains:

| Section | Content |
|---|---|
| Header | Project name, session metadata, dual coverage metrics, quality summary, warnings for incomplete areas |
| §1 Introduction | Purpose, scope (Phase 3 or LLM-synthesised), definitions, references |
| §2.1 Product Perspective | Phase 3 or LLM-synthesised |
| §2.2 Product Functions | Per-domain LLM narrative summaries (one paragraph per confirmed domain) |
| §2.3 User Characteristics | Phase 3 or LLM-synthesised with Markdown table |
| §2.4 Operating Environment | Phase 3 or LLM-synthesised |
| §2.5 Assumptions & Dependencies | Phase 3 or LLM-synthesised numbered list |
| §2.6 User Documentation | LLM-synthesised from usability requirements and user profile |
| §3.1 Functional Requirements | All FRs with SMART badges, priority labels, turn/category/domain metadata |
| §3.2 External Interfaces | Phase 3 or LLM-synthesised; hardware interfaces always stubbed |
| §3.3 Performance Requirements | Extracted performance NFRs |
| §3.4 Logical Database Requirements | Architect-review stub with implied-data requirement checklist |
| §3.5 Design Constraints | Extracted CON requirements or architect-review stub |
| §3.6 System Attributes | Reliability, availability, security, maintainability, portability, usability NFRs |
| Appendix A | Traceability matrix |
| Appendix B | Coverage and SMART quality report |
| Appendix C | Conversation transcript summary |
| Appendix D | Domain-agnostic design-derived stubs for unconfirmed domains and structural gaps |

---

## Ablation Study Support

Gap detection can be disabled per session for controlled evaluation experiments.

**Via the UI:** toggle the "Gap Detection" switch before clicking Start.

**Via the API:**
```json
POST /api/session/start
{ "gap_detection": false }
```

**Programmatically:**
```python
manager = ConversationManager(provider=..., gap_enabled=False)
```

When disabled, `GapDetector` returns a full-coverage report (100%, no gaps).

---

## Configuration

| Environment Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Required for the OpenAI provider |
| `OLLAMA_API_KEY` | Required for the Ollama provider |
| `OLLAMA_BASE_URL` | Ollama base URL (default: `https://genai-01.uni-hildesheim.de/ollama`) |

Key thresholds (defined in `prompt_architect.py` / `utils.py`):

| Constant | Default | Description |
|---|---|---|
| `MIN_FUNCTIONAL_REQS` | 10 | Minimum functional requirements before Phase 2 NFR probing begins |
| `MIN_NFR_PER_CATEGORY` | 2 | Minimum measurable requirements per mandatory NFR category |

Domain gate configuration (defined in `domain_gate.py` / `domain_discovery.py`):

| Constant | Value | Description |
|---|---|---|
| `_DOMAIN_GATE_COVERAGE_FRACTION` | 0.8 | Fraction of in-scope domains that must be confirmed before the gate is satisfied |
| `RESEED_TURN` | 10 | First re-seeding pass |
| `SECOND_RESEED_TURN` | 20 | Second re-seeding pass |
| `THIRD_RESEED_TURN` | 30 | Third re-seeding pass (for complex systems) |

Context window and decomposition limits (defined in `conversation_manager.py`):

| Constant | Value | Description |
|---|---|---|
| `MAX_HISTORY_TURNS` | 10 | Number of past turns included in each LLM call |
| Decomposition cap (standard) | 3 domains/turn | Maximum domains decomposed per turn |
| Decomposition cap (complex) | 5 domains/turn | Raised cap for systems assessed as `complex` |

Session logs are written to `logs/session_<id>.json`. Projects are stored in `projects/<id>.json`. Generated SRS files are written to `output/SRS_<id>_<timestamp>.md`. All directories are created automatically on startup.

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
