# RE Assistant

**Requirements Engineering Assistant | University of Hildesheim**

An AI-powered elicitation tool that conducts structured stakeholder interviews, detects coverage gaps in real time, enforces IEEE 830-1998 completeness across functional domains and non-functional categories, and generates a full Software Requirements Specification (SRS) document.

---

## Table of Contents

- [Overview](#overview)
- [What's New in Iteration 9](#whats-new-in-iteration-9)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Running the Application](#running-the-application)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Component Reference](#component-reference)
- [SRS Output Format](#srs-output-format)
- [Testing](#testing)
- [Ablation Study Support](#ablation-study-support)
- [Configuration](#configuration)
- [Known Limitations](#known-limitations)

---

## Overview

The RE Assistant automates the requirements elicitation process through a structured conversational interview. It guides stakeholders through four phases — project scope clarification, functional domain coverage, non-functional requirement depth, and IEEE 830 documentation — producing a complete, annotated SRS document at the end.

**Key capabilities:**

- Conversational elicitation guided by a phase-aware prompt architect (no rigid scripting)
- Phase 0 scope clarification: structured questions establish project purpose, users, boundaries, and key constraints before functional elicitation begins
- Project management layer: named projects with persistent JSON storage, each linked to a session
- Dual task modes: `elicitation` (full conversational interview) and `srs_only` (SRS generation from an uploaded requirements file)
- Requirements file upload with LLM-powered preprocessing: quality check, SMART rewrite, type/category classification, atomic splitting, and domain gate seeding from uploaded content
- Dynamic functional domain gate: the LLM seeds domains from the first user message and tracks each through `unprobed → partial → confirmed`; confirmation requires both sufficient requirements **and** active probing (`probe_count >= 1`)
- Domain re-seeding at turns 10, 20, and 30, with requirement samples drawn evenly across categories for breadth in complex systems
- Template-aware requirement decomposition: per-domain coverage checklists drive gap-targeted generation; re-decomposition triggers when a domain grows by ≥ 3 requirements since the last pass
- Real-time gap detection across 14 IEEE 830 coverage categories
- NFR depth enforcement: each of 6 mandatory NFR categories requires ≥ 2 measurable requirements before advancing to Phase 3
- Phase 3 IEEE documentation: interactive collection of IEEE 830 narrative sections via `<SECTION>` tags
- SRS Coverage Enricher: fills remaining empty sections via Phase 3 answers → LLM synthesis → architect-review stubs
- SMART quality annotation and auto-rewriting for every extracted requirement
- Full IEEE 830-1998 SRS in Markdown with dual coverage metrics
- Single-page web UI with live domain gate ring, IEEE-830 ring, gap panel, and session log browser with replay
- Ablation study support: gap detection can be toggled on/off per session

---

## What's New in Iteration 9

| Feature | Description |
|---|---|
| **Phase 0: Scope Clarification** | A dedicated pre-elicitation phase (up to 10 turns) asks structured questions about project purpose, intended users, primary features, key constraints, and out-of-scope boundaries. Builds a `project_brief` dict that seeds all subsequent phases. Auto-transitions when `scope_complete = true`. |
| **Improved System Prompt Architecture** | `PromptArchitect` now separates four phases: Phase 0 (scope), Phase 1 (functional), Phase 2 (NFR), Phase 3 (IEEE). Each phase injects a tightly focused context block rather than a monolithic session dump. Coverage-hint injection uses a soft "COVERAGE HINT" framing rather than the previous mandatory "DIRECTIVE", allowing the LLM to integrate suggestions naturally. |
| **Domain Coverage Expansion** | `DomainDiscovery` re-seeding now samples up to 40 requirements distributed evenly across domain categories for better breadth. System complexity assessment (`simple` / `moderate` / `complex`) is propagated into re-seed prompts and raises the decomposition cap from 3 to 5 for complex systems. |
| **Sub-Dimension Tracking** | Each requirement is tagged with a sub-dimension (`data`, `actions`, `constraints`, `automation`, `edge_cases`). The domain context block shows per-dimension coverage so the LLM knows which angles remain unexplored without being told which specific question to ask. |
| **Structured src/ Layout** | All business logic lives under `src/components/` in self-contained subdirectories (`conversation_manager/`, `domain_discovery/`, `system_prompt/`). Each subdirectory owns its own `utils.py` and `__init__.py`. |

### Earlier Milestones (Iterations 5–8)

| Iteration | Highlights |
|---|---|
| **Iteration 8** | Phase 0 scaffold integrated; project scope stored as `project_brief` in `ConversationState`. |
| **Iteration 7** | `SRSCoverageEnricher` three-tier fill strategy (customer answers → LLM synthesis → stubs); Appendix D domain-agnostic stubs. |
| **Iteration 6** | Third re-seed pass at turn 30; `MAX_HISTORY_TURNS` reduced to 10; `system_complexity` field added. |
| **Iteration 5** | Project management layer; dual task modes; `RequirementPreprocessor`; probe-count gate redesign; `DomainGate.is_satisfied` redesign; session log browser + replay. |

---

## Architecture

```
Browser  ──POST/GET──►  Flask REST API (app.py)
                               │
                        Projects (JSON files)
                               │
                    ConversationManager
          ┌────────────────────┼──────────────────────────────┐
          │                    │                               │
   PromptArchitect      RequirementExtractor            DomainDiscovery
   (4 phases:            (<REQ> + <SECTION> tags)       (seed / reseed /
    scope/fr/nfr/ieee)          │                       match / decompose /
          │              ConversationState               classify)
   LLMProvider                  │                              │
 (OpenAI/Ollama/Stub)     SRSTemplate                   DomainGate
                                │                       (is_satisfied)
                          SRSFormatter
                                │
               RequirementPreprocessor    GapDetector
               (upload pipeline)          (14 IEEE-830 categories +
                                           domain gate gap injection)
                                │
                     SRSCoverageEnricher
                     (3-tier section fill)
```

**Request flow per turn (`elicitation` mode):**

1. `determine_elicitation_phase(state)` returns `scope` | `fr` | `nfr` | `ieee`
2. `PromptArchitect.build_system_message()` builds a phase-focused context block: scope questions (Phase 0), domain gate status + checklist (Phase 1), NFR category depth (Phase 2), IEEE section completion (Phase 3)
3. The LLM produces visible text with embedded `<REQ>` tags (and `<SECTION>` tags in Phase 3)
4. `RequirementExtractor` parses all tags; Phase 3 sections are committed to `state.srs_section_content`
5. SMART quality check batch-processes all newly extracted requirements, rewriting those that fail Specific or Measurable criteria
6. `DomainDiscovery` LLM-matches each requirement to a domain, classifies its NFR category and sub-dimension, and runs decomposition for any domain with ≥ 2 requirements
7. Domain gate status is updated: `confirmed` requires ≥ 3 requirements **and** `probe_count >= 1`
8. Domain gate re-seeding runs at turns 10, 20, and 30
9. `SRSTemplate.update_from_requirements()` syncs the template
10. `GapDetector.analyse()` produces a `GapReport`, injecting synthetic gaps for unprobed/partial domains
11. The API returns the assistant reply, gap report, current phase, and dual coverage metrics

**At session end:**

1. `SRSCoverageEnricher.enrich()` fills remaining empty sections (Phase 3 answers → LLM synthesis → stubs)
2. `SRSFormatter.write()` renders the full IEEE 830 Markdown document to `output/`

---

## Project Structure

```
.
├── app.py                              # Flask REST API — 15+ endpoints, session lifecycle
├── index.html                          # Single-page web UI (107 KB)
├── requirements.txt                    # Python dependencies
├── example.env                         # Environment variable template
├── .github/
│   └── workflows/
│       └── ci.yml                      # GitHub Actions CI — Python 3.11 & 3.12, pytest, flake8
├── src/
│   ├── __init__.py
│   └── components/
│       ├── conversation_manager/
│       │   ├── conversation_manager.py # Orchestrates full session lifecycle
│       │   ├── llm_provider.py         # OpenAI / Ollama / Stub provider abstraction
│       │   ├── session_logger.py       # Per-session JSON event logging
│       │   └── utils.py                # SMART check prompt, transition messages
│       ├── domain_discovery/
│       │   ├── domain_discovery.py     # Seed / reseed / match / classify / decompose
│       │   ├── domain_gate.py          # DomainGate dataclass; is_satisfied logic
│       │   ├── domain_space.py         # DomainSpec dataclass (per-domain state)
│       │   └── utils.py                # Domain prompts and constants
│       └── system_prompt/
│           ├── prompt_architect.py     # Phase-aware system message builder
│           ├── prompt_context.py       # Context block builders per phase
│           └── utils.py                # IEEE-830 registry, NFR list, role templates
│   ├── conversation_state.py           # Session state, requirement store, coverage tracking
│   ├── requirement_extractor.py        # Parses <REQ> and <SECTION> tags; deduplicates
│   ├── requirement_preprocessor.py     # LLM-powered preprocessing for uploaded files
│   ├── gap_detector.py                 # 14-category IEEE-830 gap analysis
│   ├── question_generator.py           # Coverage-hint injection for gap-targeted probing
│   ├── srs_template.py                 # IEEE 830 data model (progressively populated)
│   ├── srs_formatter.py                # Renders SRSTemplate to Markdown (Appendices A–D)
│   └── srs_coverage.py                 # 3-tier SRS section enrichment
├── tests/
│   ├── conftest.py
│   ├── test_z_api.py                   # Flask API integration tests
│   ├── test_conversation_state.py
│   ├── test_domain_gate.py
│   ├── test_gap_detector.py
│   ├── test_requirement_extractor.py
│   ├── test_requirement_preprocessor.py
│   ├── test_srs_formatter.py
│   └── test_srs_template.py
├── projects/                           # Persistent project JSON files (auto-created)
├── logs/                               # Session JSON logs (auto-created)
└── output/                             # Generated SRS documents (auto-created)
```

---

## Installation

**Requirements:** Python 3.10+

```bash
# 1. Clone the repository
git clone <repo-url>
cd llm-re-assistant-fresh

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Copy the environment template and fill in your keys
cp example.env .env
```

**Environment variables:**

```bash
# OpenAI provider
export OPENAI_API_KEY=sk-...

# Ollama provider
export OLLAMA_API_KEY=<your-key>
export OLLAMA_BASE_URL=https://genai-01.uni-hildesheim.de/ollama   # optional, has default
```

---

## Running the Application

```bash
# Default: OpenAI GPT-4o
python app.py

# Alternative models
python app.py --provider openai --model gpt-4o-mini

# Local Ollama
python app.py --provider ollama --model llama3.1:8b

# Stub provider — no API key needed, for testing/development
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
4. The assistant progresses through four phases automatically:
   - **Phase 0 (Scope):** Structured questions about project purpose, target users, primary features, key constraints, and what is explicitly out of scope. Completes when `scope_complete = true`.
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
{ "project": { "id": "abc123", "name": "Smart Home System", "task_type": "elicitation", "created_at": "...", "req_count": 0 } }
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
  "domain_gate_status": { "user_authentication": "unprobed", "reporting": "unprobed" },
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
  "gap_report": { "critical": [...], "important": [...], "optional": [...] },
  "coverage_report": { "domain_completeness_pct": 45, "ieee_coverage_pct": 30 },
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

**Response:** `{ "srs_path": "output/SRS_a1b2c3d4_1234567890.md", "download_url": "/api/session/download_srs?session_id=a1b2c3d4" }`

---

#### `GET /api/session/download_srs?session_id=<id>`

Download the generated SRS Markdown file.

#### `GET /api/session/download_log?session_id=<id>`

Download the raw conversation log as JSON.

---

### Domain management

#### `POST /api/domain/add`
Add a custom domain to the gate.

#### `PUT /api/domain/update`
Rename an existing domain.

#### `DELETE /api/domain/delete`
Remove a domain from the gate.

#### `PUT /api/domain/mark_complete`
Mark a domain as confirmed or excluded.

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

Returns `{ "status": "ok", "provider": "openai", "version": "iteration-9" }`.

---

## Component Reference

### `ConversationManager`
(`src/components/conversation_manager/conversation_manager.py`)

Orchestrates the full session lifecycle.

- `start_session()` — creates session state, initialises `DomainGate`, returns the session tuple
- `inject_requirements()` — injects preprocessed requirements into session state; tracks NFR coverage during injection
- `seed_domains_from_preprocessed()` — seeds domain gate from category labels in uploaded requirements without an LLM call
- `send_turn()` — builds system prompt, calls LLM, extracts requirements and sections, runs SMART check, performs domain matching, NFR classification, sub-dimension tagging, decomposition, and domain status update
- `finalize_session()` — runs SRS coverage enrichment and generates the final document

**History window:** last 10 turns (`MAX_HISTORY_TURNS = 10`).

---

### `RequirementPreprocessor`
(`src/requirement_preprocessor.py`)

Accepts raw requirement strings and a project context. Calls the LLM once per batch to:

- Classify each requirement as `functional`, `non_functional`, or `constraint`
- Assign a category key and human-readable label
- Assign a SMART score (1–5)
- Rewrite vague requirements to be measurable
- Split compound requirements into atomic items

Returns a `PreprocessResult` with `ProcessedRequirement` objects carrying `final_text`, `req_type`, `category`, `category_label`, `smart_score`, `was_rewritten`, and `was_split`.

---

### `DomainDiscovery`
(`src/components/domain_discovery/domain_discovery.py`)

**Seeding (`seed()`):** Called on turn 1. The LLM infers 8–15 functional domain labels from the stakeholder's first message.

**Seeding from labels (`seed_from_labels()`):** Seeds the gate from a known label list without an LLM call. Used with uploaded requirements.

**Re-seeding (`reseed()`):** At turns 10, 20, and 30. Samples up to 40 requirements evenly across domain categories. System complexity is included in the re-seed prompt.

**Domain matching (`match_requirement_to_domain()`):** LLM-matches each requirement to a domain key; falls back to partial key string matching.

**NFR classification (`classify_nfr()`):** Maps non-functional requirements to one of 6 mandatory categories. Checks the `<REQ category="...">` tag first before calling the LLM.

**Sub-dimension classification (`classify_subdimension()`):** Tags each requirement as `data`, `actions`, `constraints`, `automation`, or `edge_cases`.

**Decomposition (`decompose_requirements()`):** Generates missing atomic requirements guided by per-domain coverage templates. `[NFR]`-prefixed output is stored as `NON_FUNCTIONAL`. Re-runs whenever the domain has grown by ≥ 3 since the last pass (`decompose_count` tracks passes).

**Domain status transitions:**

| Transition | Condition |
|---|---|
| `unprobed` → `partial` | ≥ 1 requirement matched |
| `partial` → `confirmed` | ≥ 3 requirements **AND** `probe_count >= 1` |
| any → `excluded` | Stakeholder marks domain out of scope |

---

### `DomainGate`
(`src/components/domain_discovery/domain_gate.py`)

Central data structure tracking functional domain coverage state.

**`is_satisfied`** — single source of truth for gate completion. Requires:
1. Gate has been seeded and has at least one domain.
2. ≥ 80% of in-scope (non-excluded) domains are `confirmed`.
3. Every in-scope unconfirmed domain has `probe_count >= 1`.

**`completeness_pct`** — `confirmed_count / active_count × 100`, where `active_count` excludes excluded domains.

---

### `PromptArchitect`
(`src/components/system_prompt/prompt_architect.py`)

Builds a phase-specific system message on every turn.

**Phase 0 (Scope):** Role block + scope clarification questions targeting purpose, users, features, constraints, and boundaries.

**Phase 1 (FR):** Role block + `_build_domain_context()` — domain requirement counts, per-domain coverage checklist with `[COVERED] / [PENDING] / [OUT-OF-SCOPE]`, remaining domain list.

**Phase 2 (NFR):** Role block + `_build_nfr_context()` — current NFR category, coverage count vs threshold, probe hints, example requirements, status of all 6 categories.

**Phase 3 (IEEE):** Role block + `_build_ieee_section_context()` — current uncovered section, suggested question, completed vs remaining sections, total requirement counts.

**SRS-only mode:** `_build_srs_only_message()` — always `ieee` phase, includes compact requirements summary.

---

### `GapDetector`
(`src/gap_detector.py`)

Analyses `ConversationState` and returns a `GapReport` across 14 IEEE 830 categories. NFR categories use `state.nfr_coverage` counts against `MIN_NFR_PER_CATEGORY`. Structural categories use keyword matching against the full conversation corpus plus `state.covered_categories`.

**Domain gate gap injection:** Unprobed and partial domains are injected as synthetic critical gaps with their pre-generated probe question.

**Coverage-hint injection:** `question_generator.py` selects the highest-priority gap and appends a `── COVERAGE HINT ──` block to the system prompt — a suggested question framed as optional guidance rather than a command.

---

### `RequirementExtractor`
(`src/requirement_extractor.py`)

Parses `<REQ type="..." category="..."> ... </REQ>` tags from LLM responses. Falls back to numbered `Requirement N (Type):` patterns, then bare `The system shall ...` sentences. Deduplicates by normalised text before committing to state.

**Phase 3:** `extract_sections()` parses `<SECTION id="X.Y"> ... </SECTION>` tags. `commit_sections()` stores content in `state.srs_section_content` and marks sections covered in `state.phase4_sections_covered`. Appends to existing content if a section is revisited.

---

### `SRSCoverageEnricher`
(`src/srs_coverage.py`)

Fills empty IEEE 830 sections before document rendering using a three-tier strategy:

1. **Phase 3 customer answers (highest priority):** The customer's own words are used verbatim.
2. **LLM synthesis (low-risk sections):** Scope, product perspective, product functions, user classes, assumptions, operating environment, user documentation, interfaces — all synthesised from elicited requirements. Every inferred statement is marked `[INFERRED]`.
3. **Architect-review stubs (high-risk sections):** Hardware interfaces, logical database requirements, and design constraints always receive clearly marked stubs. Never LLM-fabricated.

`§2.2 Product Functions` is special: a dedicated LLM call per confirmed domain synthesises a 2–4 sentence capability description from that domain's requirements alone.

---

### `SRSFormatter`
(`src/srs_formatter.py`)

Renders `SRSTemplate` to full IEEE 830 Markdown.

- **SMART quality badges** on every requirement (`★★★ 4/5`, per-dimension breakdown, rewrite notes)
- **Appendix A — Traceability Matrix:** all requirements × (type, category, section, turn, priority, SMART score, text)
- **Appendix B — Coverage & Quality Report:** session metrics, domain gate breakdown, NFR coverage table, SMART dimension analysis, IEEE-830 category grid
- **Appendix C — Conversation Transcript Summary:** turn-by-turn excerpts (truncated for readability)
- **Appendix D — Design-Derived Requirements Inventory:** domain-agnostic `[D]`-tagged stubs for unconfirmed domains and uncovered structural sections

---

## SRS Output Format

Generated documents are saved to `output/` as `SRS_<session_id>_<timestamp>.md`.

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
| §3.5 Design Constraints | Extracted constraint requirements or architect-review stub |
| §3.6 System Attributes | Reliability, availability, security, maintainability, portability, usability NFRs |
| Appendix A | Traceability matrix |
| Appendix B | Coverage and SMART quality report |
| Appendix C | Conversation transcript summary |
| Appendix D | Domain-agnostic design-derived stubs for unconfirmed domains and structural gaps |

---

## Testing

The test suite lives in `tests/` and is run via pytest.

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src tests/

# Run a specific file
pytest tests/test_domain_gate.py -v
```

**Test files:**

| File | Coverage |
|---|---|
| `test_conversation_state.py` | Session state lifecycle and coverage tracking |
| `test_domain_gate.py` | Domain gate state transitions and `is_satisfied` logic |
| `test_gap_detector.py` | Gap analysis across all 14 IEEE-830 categories |
| `test_requirement_extractor.py` | `<REQ>` / `<SECTION>` parsing and deduplication |
| `test_requirement_preprocessor.py` | LLM preprocessing pipeline (with stub provider) |
| `test_srs_template.py` | IEEE 830 data model and SMART heuristics |
| `test_srs_formatter.py` | Markdown rendering and appendix output |
| `test_z_api.py` | Flask API integration — projects, sessions, domains, logs |

**CI/CD:** GitHub Actions runs the full suite on Python 3.11 and 3.12 on every push. Flake8 linting and dependency caching are included (see `.github/workflows/ci.yml`).

---

## Ablation Study Support

Gap detection can be disabled per session for controlled evaluation experiments.

**Via the UI:** toggle the "Gap Detection" switch before clicking Start.

**Via the API:**
```json
POST /api/session/start
{ "gap_detection": false }
```

When disabled, `GapDetector` returns a full-coverage report (100%, no gaps), allowing a controlled comparison of elicitation quality with and without gap guidance.

---

## Configuration

**Environment variables:**

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Required for the OpenAI provider |
| `OLLAMA_API_KEY` | Required for the Ollama provider |
| `OLLAMA_BASE_URL` | Ollama base URL (default: `https://genai-01.uni-hildesheim.de/ollama`) |

**Elicitation thresholds** (defined in `src/components/system_prompt/utils.py`):

| Constant | Default | Description |
|---|---|---|
| `MIN_FUNCTIONAL_REQS` | 10 | Minimum FRs before Phase 2 NFR probing begins |
| `MIN_NFR_PER_CATEGORY` | 2–3 | Minimum measurable requirements per mandatory NFR category |

**Domain gate** (defined in `src/components/domain_discovery/`):

| Constant | Value | Description |
|---|---|---|
| `_DOMAIN_GATE_COVERAGE_FRACTION` | 0.8 | Fraction of in-scope domains that must be confirmed |
| `RESEED_TURN` | 10 | First re-seeding pass |
| `SECOND_RESEED_TURN` | 20 | Second re-seeding pass |
| `THIRD_RESEED_TURN` | 30 | Third re-seeding pass (complex systems) |

**Context window and decomposition** (defined in `src/components/conversation_manager/conversation_manager.py`):

| Constant | Value | Description |
|---|---|---|
| `MAX_HISTORY_TURNS` | 10 | Past turns included per LLM call |
| Decomposition cap (standard) | 3 domains/turn | Maximum domains decomposed per turn |
| Decomposition cap (complex) | 5 domains/turn | Raised for systems assessed as `complex` |

Session logs → `logs/session_<id>.json`. Projects → `projects/<id>.json`. SRS documents → `output/SRS_<id>_<timestamp>.md`. All directories are created automatically on startup.

---

## Known Limitations

- **Session persistence:** Sessions are stored in memory only. Restarting the server loses all active sessions. Projects are persisted to disk but their linked in-memory sessions are not.
- **LLM call volume:** Multiple LLM calls are made per turn — domain matching (one per extracted requirement), NFR classification, sub-dimension classification, SMART batch check, and optionally decomposition and probe question generation. High-latency providers cause noticeable turn delays.
- **Domain gate seeding quality:** Seed accuracy depends on the richness of the first user message. Vague opening messages may yield a generic domain list. Re-seeding at turns 10, 20, and 30 partially compensates.
- **Probe-count dependency:** `confirmed` state requires active probing. In `srs_only` mode or after uploading requirements, domains seeded from labels remain `partial` until the conversation probes them, which may slow phase advancement.
- **SMART heuristics:** The heuristic check in `srs_template.py` uses lightweight keyword and regex patterns. The LLM-based batch check supersedes it for actively extracted requirements, but decomposition-generated requirements rely on heuristics only.
- **Requirement extraction reliability:** The extractor depends on the LLM consistently emitting well-formed `<REQ>` and `<SECTION>` tags. Malformed or missing tags trigger weaker fallback patterns.
- **High-risk section stubs:** Hardware interfaces, logical database requirements, and design constraints are always stubbed and require manual completion by a system architect before the SRS can be used for development.
- **Single-user, no authentication:** Not intended for multi-user or production deployment.

---

*RE Assistant | University of Hildesheim*
