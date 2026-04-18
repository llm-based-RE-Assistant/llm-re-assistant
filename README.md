# RE Assistant

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

The RE Assistant automates the requirements elicitation process through a structured conversational interview. It guides stakeholders through three phases — functional domain coverage, non-functional requirement depth, and IEEE 830 documentation — producing a complete, annotated SRS document at the end.

**Key capabilities:**

- Conversational elicitation guided by a phase-aware prompt architect (no rigid scripting)
- Project management layer: named projects with persistent JSON storage, each linked to a session
- Dual task modes: `elicitation` (full conversational interview) and `srs_only` (SRS generation from an uploaded requirements file)
- Requirements file upload with LLM-powered preprocessing: quality check, SMART rewrite, type/category classification, atomic splitting, and domain gate seeding from uploaded content
- Dynamic functional domain gate: the LLM seeds domains from the first user message and tracks each through `unprobed → partial → confirmed`; domain status requires both sufficient requirements **and** active probing (`probe_count >= 1`)
- Domain re-seeding at turns 10, 20, and 30, with requirement samples drawn evenly across categories for better signal breadth in complex systems
- Template-aware requirement decomposition: per-domain coverage checklists drive gap-targeted generation; re-decomposition is allowed when a domain grows by ≥ 3 requirements since the last pass
- Real-time gap detection across 14 IEEE 830 coverage categories
- NFR depth enforcement: each of 6 mandatory NFR categories requires ≥ 2 measurable requirements before advancing to Phase 3
- Phase 3 IEEE documentation: interactive collection of IEEE 830 narrative sections via `<SECTION>` tags
- SRS Coverage Enricher: fills remaining empty sections via Phase 3 answers → LLM synthesis → architect-review stubs
- SMART quality annotation and auto-rewriting for every extracted requirement
- Full IEEE 830-1998 SRS in Markdown with dual coverage metrics
- Single-page web UI with live domain gate ring, IEEE-830 ring, gap panel, and session log browser with replay
- Ablation study support: gap detection can be toggled on/off per session

---

## What's New in Iteration 5

| Feature | Description |
|---|---|
| **Project Management Layer** | Named projects are persisted as JSON files in `projects/`. Each project holds a name, description, task type, linked session ID, and requirement count. The UI can list, create, update, and delete projects. Sessions link back to their parent project and update its `req_count` after every turn. |
| **Dual Task Modes** | `task_type` parameter on session start selects the operating mode. `elicitation` runs the full conversational interview. `srs_only` skips domain seeding and moves directly to IEEE-830 documentation collection, intended for use after uploading a pre-existing requirements file. |
| **Requirements File Upload** | `/api/session/upload_requirements` accepts `.txt` or `.json` content, runs LLM preprocessing (SMART rewrite, type/category assignment, atomic splitting), injects results into session state, and seeds the domain gate from discovered functional category labels — without a single LLM domain-seed call. |
| **`RequirementPreprocessor`** | New component (`requirement_preprocessor.py`). Parses raw requirement lines, calls the LLM once per batch for classification and rewriting, returns typed `ProcessedRequirement` objects with `req_type`, `category`, `category_label`, `smart_score`, `was_rewritten`, and `was_split` flags. |
| **Probe-Count Gate for Domain Confirmation** | A domain now transitions to `confirmed` only when it has ≥ 3 requirements **and** `probe_count >= 1`. This prevents decomposed or domain-matched requirements from silently confirming domains the RE assistant has never actively asked about, which previously caused premature phase advancement. |
| **Domain Gate `is_satisfied` Redesign** | `DomainGate.is_satisfied` now requires: (1) ≥ 80 % of in-scope (non-excluded) domains confirmed, AND (2) every in-scope unconfirmed domain has been probed at least once. This is the single source of truth used by both `determine_elicitation_phase()` and `ConversationState.is_ready_for_srs()`. |
| **Coverage-Hint Prompt Injection** | `question_generator.py` is redesigned. The mandatory "DIRECTIVE" injection is replaced with a softer "COVERAGE HINT" block. The LLM is informed about a gap and given a suggested question but is trusted to integrate it naturally rather than being commanded to ask it verbatim. |
| **Template-Aware Decomposition (re-entrant)** | `decompose_requirements()` receives a per-domain coverage checklist derived from the domain template. The [NFR] prefix in generated text signals quality-attribute requirements; these are stored with `RequirementType.NON_FUNCTIONAL` and their NFR category is classified separately. `decompose_count` (int) replaces the old `decomposed` (bool), allowing re-decomposition whenever the domain has grown by ≥ 3 requirements since the last pass. |
| **Three-Phase Prompt Architecture** | `PromptArchitect` now explicitly separates three phases: Phase 1 — functional requirement elicitation by domain (`fr`), Phase 2 — NFR depth coverage (`nfr`), Phase 3 — IEEE-830 documentation sections (`ieee`). Each phase receives a focused context block (`_build_domain_context`, `_build_nfr_context`, `_build_ieee_section_context`) rather than a single monolithic session context. |
| **Domain Coverage Checklist in Prompt** | In Phase 1, `_build_domain_context()` injects a per-domain requirement coverage checklist (if available from `state.domain_req_templates`). The LLM is instructed to cross-check each dimension as `[COVERED]`, `[PENDING]`, or `[OUT-OF-SCOPE]` before writing `<REQ>` tags. |
| **Third Re-seed Pass** | `THIRD_RESEED_TURN = 30` added to `DomainDiscovery`. Useful for complex systems where late-discovered domains (compliance, billing, admin) only become apparent after extended elicitation. |
| **Requirements Sample Breadth** | `_build_req_sample()` samples up to 40 requirements (increased from 15) distributed evenly across domain categories, ensuring the re-seed LLM call sees signal breadth rather than only early-mentioned domains. |
| **Domain Gate Seeding from Labels** | `seed_from_labels()` allows the domain gate to be seeded directly from a known list of label strings (e.g., extracted from uploaded requirements) without an LLM call. |
| **Session Log Browser & Replay** | `/api/logs` returns metadata for all session logs, filtering to logs belonging to the current project. `/api/logs/<id>/replay` returns full conversation turns from live memory or from disk, including domain gate and NFR coverage snapshots. `/api/logs/<id>/download` allows raw log download. |
| **Appendix D — Domain-Agnostic Stubs** | `srs_formatter.py` Appendix D no longer contains hard-coded DigitalHome-specific expected-requirement lists from Iteration 4. Each unconfirmed domain now receives a generic, domain-agnostic stub block tagged `[D]` telling the architect what kind of requirements to look for, derived from the domain label and status. |
| **Domain Completeness Pct Fix** | `completeness_pct` is now computed as `confirmed_count / active_count` (confirmed ÷ in-scope), not `done_count / total`. This correctly excludes excluded domains from the denominator and prevents the metric from over-reporting in systems with many out-of-scope domains. |
| **System Complexity Tracking** | `ConversationState` carries a `system_complexity` field (set by `DomainDiscovery`). The FR phase context block shows the complexity label. Decomposition cap is raised to 5 (from 3) for systems assessed as `complex`. |
| **Reduced History Window** | `MAX_HISTORY_TURNS = 10` (reduced from 20) to keep LLM context tight and reduce token cost per turn without losing conversational continuity. |

---

## Architecture

```
Browser  ──POST/GET──►  Flask REST API (app.py)
                               │
                        Projects (JSON files)
                               │
                    ConversationManager
          ┌────────────────────┼──────────────────────────┐
          │                    │                           │
   PromptArchitect      RequirementExtractor        DomainDiscovery
   (phase-aware:         (REQ + SECTION tags)       (seed / reseed /
    fr / nfr / ieee)           │                    match / decompose /
          │              ConversationState           classify)
   LLMProvider                 │                           │
 (OpenAI/Ollama/Stub)    SRSTemplate                DomainGate
                               │                    (is_satisfied)
                         SRSFormatter
                               │
                   RequirementPreprocessor    GapDetector
                   (upload pipeline)          (IEEE-830 gaps +
                                               domain gate gaps)
                               │
                    SRSCoverageEnricher
```

**Request flow per turn (`elicitation` mode):**

1. `PromptArchitect.build_system_message()` determines the current phase (`fr` / `nfr` / `ieee`) and builds a focused context block: domain gate status + coverage checklist in Phase 1, NFR category depth in Phase 2, section completion status in Phase 3
2. The LLM produces a response containing visible text plus embedded `<REQ>` tags (and `<SECTION>` tags in Phase 3)
3. `RequirementExtractor` parses all `<REQ>` tags; in Phase 3, also parses `<SECTION>` tags and commits them to `state.srs_section_content`
4. The SMART quality check batch-processes all newly extracted requirements, rewriting those that fail Specific or Measurable criteria
5. `DomainDiscovery` LLM-matches each requirement to a domain, classifies its NFR category and sub-dimension, and runs decomposition for any domain with ≥ 2 requirements (re-runs when domain grows by ≥ 3 since last pass)
6. Domain gate status is updated: `confirmed` requires ≥ 3 requirements **and** `probe_count >= 1`
7. Domain gate re-seeding runs at turns 10, 20, and 30
8. `SRSTemplate.update_from_requirements()` syncs the template
9. `GapDetector.analyse()` produces a `GapReport`, injecting synthetic gaps for unprobed/partial domains
10. The API returns the assistant reply, gap report, current phase, and dual coverage metrics to the UI

**At session end:**

1. `SRSCoverageEnricher.enrich()` fills remaining empty sections (Phase 3 answers → LLM synthesis → stubs)
2. `SRSFormatter.write()` renders the full IEEE 830 Markdown document

---

## Project Structure

```
.
├── app.py                      # Flask REST API, project management routes, session lifecycle
├── index.html                  # Single-page web UI
├── conversation_manager.py     # Orchestrates the full elicitation session and upload pipeline
├── conversation_state.py       # Session state, requirement store, coverage tracking
├── prompt_architect.py         # Phase-aware system message builder; IEEE 830 registry
├── prompt_context.py           # Context block builders per phase; phase determination logic
├── domain_discovery.py         # Domain gate seeding, re-seeding, matching, decomposition, NFR classification
├── domain_gate.py              # DomainGate dataclass; is_satisfied logic
├── domain_space.py             # DomainSpec dataclass (per-domain state, sub-dimensions)
├── gap_detector.py             # Coverage checklist and gap analysis across 14 IEEE-830 categories
├── question_generator.py       # Coverage-hint injection for gap-targeted probing
├── requirement_extractor.py    # Parses <REQ> and <SECTION> tags; deduplicates; commits to state
├── requirement_preprocessor.py # LLM-powered preprocessing for uploaded requirements files
├── srs_template.py             # IEEE 830 SRS data model (progressively populated)
├── srs_formatter.py            # Renders SRSTemplate to Markdown (incl. Appendices A–D)
├── srs_coverage.py             # Fills empty SRS sections (Phase 3 / LLM synthesis / stubs)
├── llm_provider.py             # OpenAI, Ollama, and Stub provider implementations
├── session_logger.py           # Per-session JSON event logging
├── utils.py                    # Shared utility functions (similarity, SMART check prompt)
├── projects/                   # Persistent project JSON files (auto-created)
├── logs/                       # Session JSON logs (auto-created)
└── output/                     # Generated SRS documents (auto-created)
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

# 4. Set your API key
export OPENAI_API_KEY=sk-...
# or for Ollama
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

# Stub provider (no API key needed — for testing/development)
python app.py --provider stub

# Custom host / port
python app.py --host 0.0.0.0 --port 8080 --debug
```

Then open **http://127.0.0.1:5000** in your browser.

### CLI options

| Flag | Default | Description |
|---|---|---|
| `--provider` | `openai` | LLM provider: `openai`, `ollama`, `stub` |
| `--model` | `gpt-4o` | Model name passed to the provider |
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `5000` | Port |
| `--debug` | off | Enable Flask debug mode |

---

## Usage

### Elicitation mode (full interview)

1. Open the web UI, create or select a **Project**, and click **Start Elicitation Session**.
2. Describe your software system — its purpose, intended users, and key features.
3. Respond to the assistant's questions. After each turn, the UI updates:
   - **Domain ring** (left panel, primary) — percentage of functional domains confirmed
   - **IEEE-830 ring** (left panel, secondary) — percentage of structural categories covered
   - **Domains tab** — per-domain status icons and requirement counts
   - **Gaps panel** — uncovered categories ranked by severity
4. The assistant progresses through three phases automatically:
   - **Phase 1 (FR):** Domain-by-domain functional elicitation; the prompt includes a per-domain coverage checklist with `[COVERED] / [PENDING] / [OUT-OF-SCOPE]` cross-check
   - **Phase 2 (NFR):** Once the domain gate is satisfied and ≥ 10 functional requirements exist, collect ≥ 2 measurable requirements for each of 6 mandatory NFR categories
   - **Phase 3 (IEEE):** Complete IEEE 830 narrative documentation sections interactively
5. Once all gates are satisfied, click **Generate SRS** or use the banner.
6. Click **Download** to save the Markdown SRS file.

### SRS-only mode (from uploaded requirements)

1. Create a project with `task_type = "srs_only"`.
2. Start a session and use **Upload Requirements** to send a `.txt` or `.json` file.
3. The preprocessor classifies and rewrites each requirement; the domain gate is seeded from discovered categories.
4. The assistant moves directly to Phase 3 (IEEE documentation sections) — no functional elicitation loop.
5. Generate the SRS once all IEEE sections are covered.

### Requirement tagging

The assistant wraps formalised requirements in XML tags extracted automatically:

```xml
<REQ type="functional" category="temperature_control">
The system shall allow users to set a target temperature between 10°C and 30°C for each zone.
</REQ>
```

Supported types: `functional`, `non_functional`, `constraint`

Supported categories: `functional`, `performance`, `usability`, `security_privacy`, `reliability`, `compatibility`, `maintainability`, `interfaces`, `constraints`, `stakeholders`, `scope`, `purpose`

### Section tagging (Phase 3)

During Phase 3, the assistant emits IEEE 830 narrative sections:

```xml
<SECTION id="2.3">
The system serves two primary user classes. Regular Users interact with the mobile
application to monitor and control household devices. The Administrator configures
system-wide settings and manages user accounts.
</SECTION>
```

Supported section IDs: `1.2`, `2.1`, `2.3`, `2.4`, `2.5`, `3.1.1`, `3.1.3`, `3.1.4`

---

## API Reference

All endpoints accept and return JSON.

### Projects

#### `GET /api/projects`
List all projects with lightweight card data (id, name, description, task_type, created_at, req_count).

#### `POST /api/projects/create`
Create a new project.

**Request:**
```json
{ "name": "Smart Home System", "description": "IoT home automation", "task_type": "elicitation" }
```

**Response:**
```json
{ "project": { "id": "abc123", "name": "Smart Home System", "task_type": "elicitation", ... } }
```

#### `GET /api/projects/<project_id>`
Get a single project by ID.

#### `PUT /api/projects/<project_id>`
Update project name or description.

#### `DELETE /api/projects/<project_id>`
Delete a project.

---

### Session lifecycle

#### `POST /api/session/start`

Start a new elicitation or SRS-only session.

**Request body:**
```json
{
  "gap_detection": true,
  "task_type": "elicitation",
  "project_id": "abc123"
}
```

**Response:**
```json
{
  "session_id": "a1b2c3d4",
  "opening_message": "Hello! I'm your Requirements Engineering assistant...",
  "gap_detection": true,
  "provider": "openai",
  "task_type": "elicitation"
}
```

---

#### `POST /api/session/upload_requirements`

Upload a requirements file for preprocessing and injection into session state.

**Request body:**
```json
{
  "session_id": "a1b2c3d4",
  "filename": "requirements.txt",
  "content": "FR1: The system shall ...\nFR2: ..."
}
```

**Response:**
```json
{
  "session_id": "a1b2c3d4",
  "injected": 42,
  "total_input": 44,
  "total_output": 42,
  "rewritten": 7,
  "split": 2,
  "domains_found": ["User Authentication", "Reporting"],
  "nfr_cats_found": ["performance", "security_privacy"],
  "functional_count": 30,
  "nfr_count": 12,
  "domain_gate_status": { "user_authentication": "unprobed", ... },
  "requirements_preview": [...]
}
```

---

#### `POST /api/session/turn`

Send one user message and receive the assistant reply.

**Request body:**
```json
{ "session_id": "a1b2c3d4", "message": "The system needs to support multiple zones." }
```

**Response:**
```json
{
  "session_id": "a1b2c3d4",
  "assistant_reply": "...",
  "turn_id": 3,
  "gap_report": { ... },
  "coverage_report": { ... },
  "srs_ready": false,
  "current_phase": "fr",
  "task_type": "elicitation"
}
```

---

#### `GET /api/session/status?session_id=<id>`

Returns turn count, session state, coverage report, gap report, and current phase.

---

#### `POST /api/session/generate_srs`

Finalise the session and generate the SRS document.

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

- **Session persistence:** Sessions are stored in memory only. Restarting the server loses all active sessions. Projects are persisted to disk but their linked in-memory sessions are not.
- **LLM call volume:** Multiple LLM calls are made per turn — domain matching (one per extracted requirement), NFR classification, sub-dimension classification, SMART batch check, and optionally decomposition and probe question generation. High-latency providers will cause noticeable turn delays.
- **Domain gate seeding quality:** Seed accuracy depends on the richness of the first user message. Vague opening messages may yield a generic or incomplete domain list. Re-seeding at turns 10, 20, and 30 partially compensates.
- **Probe-count dependency:** The `confirmed` state now requires active probing. In `srs_only` mode or after uploading requirements, domains seeded from labels will remain `partial` until the conversation probes them, which may slow phase advancement.
- **SMART heuristics:** The heuristic check in `srs_template.py` uses lightweight keyword and regex patterns. The LLM-based batch check in `conversation_manager.py` supersedes it for all actively extracted requirements, but requirements added via decomposition rely on the heuristic only.
- **Requirement extraction reliability:** The extractor depends on the LLM consistently emitting well-formed `<REQ>` and `<SECTION>` tags. Malformed or missing tags trigger weaker fallback patterns.
- **High-risk section stubs:** Hardware interfaces, logical database requirements, and design constraints are always stubbed and require manual completion by a system architect before the SRS can be used for development.
- **Single-user, no authentication:** Not intended for multi-user or production deployment.

---

*RE Assistant | University of Hildesheim*