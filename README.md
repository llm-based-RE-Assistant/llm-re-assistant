# RE Assistant — Iteration 4

**Requirements Engineering Assistant | University of Hildesheim**

An AI-powered elicitation tool that conducts structured stakeholder interviews, detects coverage gaps in real time, enforces IEEE 830-1998 completeness across functional domains and non-functional categories, and generates a full Software Requirements Specification (SRS) document.

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

The RE Assistant automates the requirements elicitation process through a structured conversational interview. It guides the user through four phases — context gathering, functional domain coverage, non-functional requirement depth, and IEEE 830 documentation — producing a complete, annotated SRS document at the end.

**Key capabilities:**

- Conversational elicitation guided by a coverage-aware prompt architect (no rigid scripting)
- Dynamic functional domain gate: the LLM seeds domains from the first user message and tracks each through `unprobed → partial → confirmed`
- Real-time gap detection across 14 IEEE 830 coverage categories
- NFR depth enforcement: each of 6 mandatory NFR categories requires ≥ 2 measurable requirements before moving to the next phase
- Phase 4 documentation: interactive collection of 8 IEEE 830 narrative sections via `<SECTION>` tags
- SRS Coverage Enricher: fills remaining empty sections via Phase 4 answers → LLM synthesis → architect-review stubs
- SMART quality annotation and auto-rewriting for every extracted requirement
- Requirement decomposition: auto-generates missing atomic requirements for confirmed domains
- Full IEEE 830-1998 SRS in Markdown with dual coverage metrics
- Single-page web UI with live domain gate ring, IEEE-830 ring, gap panel, and follow-up question panel
- Ablation study support: gap detection can be toggled on/off per session

---

## What's New in Iteration 4

| Feature | Description |
|---|---|
| **Dynamic Domain Gate** | LLM seeds 8–15 functional domains from the first stakeholder message. Each domain transitions through `unprobed → partial → confirmed` states based on requirement count thresholds (≥ 1 req = partial, ≥ 3 reqs = confirmed). Gate must be satisfied before SRS generation is unlocked. |
| **Domain Re-seeding** | At turn 10 and turn 20, the domain list is automatically extended with any functional areas implied by requirements captured so far but not yet in the gate. |
| **LLM Domain Matching** | Each extracted requirement is matched to a domain via a dedicated LLM call against the full domain key list, replacing rule-based heuristics. Falls back to partial key string matching. |
| **Requirement Decomposition** | For every domain with ≥ 2 requirements, the LLM generates 2–5 missing atomic requirements covering data, actions, constraints, automation, and edge cases. Deduplication prevents near-duplicate additions (Jaccard similarity > 0.6 threshold). |
| **NFR Depth Enforcement (Phase 3)** | Each of 6 mandatory NFR categories (`performance`, `usability`, `security_privacy`, `reliability`, `compatibility`, `maintainability`) requires ≥ 2 measurable requirements. The coverage-aware prompt guides the LLM to probe weak categories naturally. |
| **SMART Quality Check & Auto-Rewrite** | After extraction, each batch of requirements is sent to a dedicated LLM quality check. Requirements failing Specific or Measurable criteria are automatically rewritten with concrete numbers. All requirements are scored 1–5 across 5 SMART dimensions. |
| **Phase 4 — IEEE 830 Documentation** | After all NFR categories reach depth ≥ 2, the assistant asks 8 structured questions to populate IEEE 830 narrative sections (scope, user classes, operating environment, assumptions, user/software/communication interfaces, product perspective). Answers are captured via `<SECTION id="X.Y">` tags. |
| **SRS Coverage Enricher** | `srs_coverage.py` fills empty IEEE 830 sections at session end: Phase 4 customer answers take priority; LLM synthesis fills low-risk sections; hardware interfaces, database requirements, and design constraints always receive architect-review stubs. |
| **Sub-dimension Tagging** | Each requirement is classified into one of five sub-dimensions (`data`, `actions`, `constraints`, `automation`, `edge_cases`) for intra-domain depth tracking. |
| **Coverage-Aware Prompt Architecture** | The system prompt provides a live session context block showing domain gate status, NFR depth per category, and Phase 4 section progress. The LLM is trusted to surface gaps naturally rather than following a rigid command sequence. |
| **Dual Metric UI** | The left panel shows two independent coverage rings: domain gate completeness and IEEE-830 structural coverage. The Domains tab lists each domain with live status icons and requirement counts. |
| **Duplicate Detection** | Jaccard similarity check prevents semantically duplicate requirements from being added during decomposition (threshold: > 0.6). |

---

## Architecture

```
Browser  ──POST/GET──►  Flask REST API (app.py)
                               │
                    ConversationManager
                    ┌──────────┼──────────────────┐
                    │          │                   │
             PromptArchitect   │        RequirementExtractor
                    │          │                   │
               LLMProvider     │           ConversationState
          (OpenAI/Ollama/Stub)  │                   │
                    │          │              SRSTemplate
                    │          │                   │
             DomainDiscovery   │            SRSFormatter
           (seed/reseed/match/ │
            decompose/classify)│
                    │          │
             GapDetector       │
                               │
                    SRSCoverageEnricher
```

**Request flow per turn:**

1. `PromptArchitect` builds the system message with a live context block containing domain gate status, NFR depth per category, and Phase 4 section progress
2. The LLM produces a response containing visible text plus embedded `<REQ>` tags (and `<SECTION>` tags in Phase 4)
3. `RequirementExtractor` parses all `<REQ>` tags; in Phase 4, also parses `<SECTION>` tags and commits them to `state.srs_section_content`
4. The SMART quality check batch-processes all newly extracted requirements, rewriting those that fail Specific or Measurable criteria
5. `DomainDiscovery` LLM-matches each requirement to a domain, classifies its NFR category and sub-dimension, and runs decomposition for any newly confirmed domain
6. Domain gate re-seeding runs automatically at turns 10 and 20
7. `SRSTemplate.update_from_requirements()` syncs the template
8. `GapDetector.analyse()` produces a `GapReport`, injecting synthetic gaps for unprobed/partial domains
9. The API returns the assistant reply, gap report, and dual coverage metrics to the UI

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
├── question_generator.py     # Proactive follow-up question generation (currently disabled by default)
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

1. Open the web UI and optionally toggle **Gap Detection** on or off.
2. Click **Start Elicitation Session**.
3. Describe your software system — its purpose, intended users, and key features.
4. Respond to the assistant's questions. After each turn, the UI updates:
   - **Domain ring** (left panel, primary) — percentage of functional domains confirmed or excluded
   - **IEEE-830 ring** (left panel, secondary) — percentage of structural categories covered
   - **Domains / IEEE-830 tab** (left panel) — per-domain or per-category status with icons and requirement counts
   - **Gaps panel** (right panel) — uncovered categories ranked by severity
5. The assistant automatically progresses through four phases:
   - **Phase 1 & 2:** Explore functional areas; the LLM uses the domain gate to identify uncovered domains and probe them with plain-language questions
   - **Phase 3:** Once ≥ 10 functional requirements are elicited, collect ≥ 2 measurable requirements for each of 6 mandatory NFR categories
   - **Phase 4:** Complete 8 IEEE 830 narrative documentation sections interactively
6. Once all gates are satisfied, click **⬇ SRS** or use the **Generate SRS** banner.
7. Click **Download** in the success banner to save the Markdown SRS file.

### Requirement tagging

The assistant wraps formalised requirements in XML tags extracted automatically:

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
The system serves two primary user classes. Regular Users interact with the mobile
application to monitor and control household devices. The Administrator configures
system-wide settings and manages user accounts. It is assumed that regular users have
basic smartphone proficiency; no technical expertise is required.
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
  "follow_up_questions": "",
  "coverage_report": {
    "domain_gate_status": { "temperature_control": "confirmed", "lighting_control": "partial", ... },
    "domain_gate_labels": { "temperature_control": "Temperature Control", ... },
    "domain_completeness_pct": 62,
    "phase4_progress": "3/8",
    "functional_count": 14,
    "nonfunctional_count": 8
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

Generate the SRS document. Requires at least 5 functional requirements.

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

Download the generated SRS Markdown file.

**Query params:** `session_id=a1b2c3d4`

---

### `GET /api/health`

```json
{ "status": "ok", "provider": "openai" }
```

---

## Component Reference

### `ConversationManager`

Central orchestrator. On each `send_turn()` call it:

1. Builds the system message via `PromptArchitect`
2. Calls the LLM (last 40 messages = 20 turns kept as context)
3. Extracts `<REQ>` and `<SECTION>` tags via `RequirementExtractor`
4. Runs the SMART batch quality check and auto-rewrite on all new requirements
5. LLM-matches each requirement to a domain, classifies NFR category and sub-dimension
6. Triggers domain re-seeding at turns 10 and 20
7. Runs decomposition for newly confirmed domains (capped at 3 domains per turn)
8. Syncs `SRSTemplate` and runs `GapDetector`

At session end (`finalize_session()`), calls `SRSCoverageEnricher.enrich()` then `SRSFormatter.write()`.

---

### `DomainDiscovery`

Manages the functional domain gate. All classification and matching uses LLM calls.

**Seeding (`seed()`):** On turn 1, identifies 8–15 functional domains from the first message. The prompt enforces domain creation for physical devices and sensors (e.g., thermostat → Temperature Control) and mandates standard system-level domains (alerts, user management, reporting).

**Re-seeding (`reseed()`):** At turns 10 and 20, inspects requirements captured so far and adds any implied domains not yet in the gate.

**Domain matching (`match_requirement_to_domain()`):** Matches each extracted requirement to a domain key via LLM. Falls back to partial key string matching.

**NFR classification (`classify_nfr()`):** Maps non-functional requirements to one of 6 mandatory categories. First checks if the `<REQ category="...">` tag already contains a valid NFR key before calling the LLM.

**Sub-dimension classification (`classify_subdimension()`):** Tags each requirement as `data`, `actions`, `constraints`, `automation`, or `edge_cases`.

**Decomposition (`decompose_requirements()`):** For confirmed domains with ≥ 2 requirements, generates 2–5 missing atomic requirements. Receives full context (both domain-specific and all other requirements) to avoid duplication. Each domain is decomposed at most once per session.

**Domain status transitions:**
- `unprobed` → `partial` (≥ 1 requirement matched)
- `partial` → `confirmed` (≥ 3 requirements matched)
- `excluded` (set when stakeholder rules a domain out of scope)

---

### `PromptArchitect`

Builds a three-block system message on every turn:

1. **ROLE block** — interviewer identity, communication style (plain language, concrete examples), measurability enforcement, one-question-per-turn rule
2. **SESSION COVERAGE AWARENESS block** — live context showing domain gate table with status icons and requirement counts, NFR coverage per category with counts vs threshold, Phase 4 section completion status, and an FR count warning when below the 10-requirement target
3. **TASK CONTRACT block** — `<REQ>` and `<SECTION>` tag format specifications, phase-by-phase guidance, and quick-reference rules

The context block is framed as *orientation* rather than commands, trusting the LLM to surface gaps naturally within the conversation flow.

---

### `GapDetector`

Analyses `ConversationState` and returns a `GapReport` across 14 IEEE 830 categories. NFR categories use `state.nfr_coverage` counts against `MIN_NFR_PER_CATEGORY = 2`. Structural categories use keyword matching against the full conversation corpus plus `state.covered_categories`.

**Domain gate gap injection:** After standard analysis, unprobed and partial domains are injected as synthetic critical gaps with their pre-generated probe question as the description. These appear as a separate "Domain Gate Gaps" group in the UI gap panel.

---

### `RequirementExtractor`

Parses `<REQ type="..." category="..."> ... </REQ>` tags from LLM responses. Falls back to numbered `Requirement N (Type):` patterns, then to bare `The system shall ...` sentences. Deduplicates by normalised text before committing to state.

**Phase 4:** `extract_sections()` parses `<SECTION id="X.Y"> ... </SECTION>` tags. `commit_sections()` stores content in `state.srs_section_content` and marks sections as covered in `state.phase4_sections_covered`. Appends to existing content if a section is revisited across multiple turns.

---

### `SRSCoverageEnricher`

Fills empty IEEE 830 sections before document rendering using a three-tier strategy:

1. **Phase 4 customer answers (highest priority):** If the customer answered a section during Phase 4, their answer is used directly.
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
- **Appendix B — Coverage & Quality Report:** session metrics, domain gate breakdown table, NFR coverage table, SMART dimension analysis, IEEE-830 category grid, requirements needing attention
- **Appendix C — Conversation Transcript Summary:** turn-by-turn user/assistant excerpts
- **Appendix D — Design-Derived Requirements Inventory:** dynamic stubs for all unconfirmed domains and uncovered structural sections with actionable architect checklists

---

## SRS Output Format

Generated documents are saved to `output/` as `SRS_<session_id>_<timestamp>.md`. Each document contains:

| Section | Content |
|---|---|
| Header | Project name, session metadata, dual coverage metrics, quality summary, warnings for incomplete areas |
| §1 Introduction | Purpose, scope (Phase 4 or LLM-synthesised), definitions, references |
| §2.1 Product Perspective | Phase 4 or LLM-synthesised |
| §2.2 Product Functions | Per-domain LLM narrative summaries (one paragraph per confirmed domain) |
| §2.3 User Characteristics | Phase 4 or LLM-synthesised with Markdown table |
| §2.4 Operating Environment | Phase 4 or LLM-synthesised |
| §2.5 Assumptions & Dependencies | Phase 4 or LLM-synthesised numbered list |
| §2.6 User Documentation | LLM-synthesised from usability requirements and user profile |
| §3.1 Functional Requirements | All FRs with SMART badges, priority labels, turn/category metadata |
| §3.2 External Interfaces | Phase 4 or LLM-synthesised; hardware interfaces always stubbed |
| §3.3 Performance Requirements | Extracted performance NFRs |
| §3.4 Logical Database Requirements | Architect-review stub with implied-data requirement checklist |
| §3.5 Design Constraints | Extracted CON requirements or architect-review stub |
| §3.6 System Attributes | Reliability, availability, security, maintainability, portability, usability NFRs |
| Appendix A | Traceability matrix |
| Appendix B | Coverage and SMART quality report |
| Appendix C | Conversation transcript summary |
| Appendix D | Design-derived stubs for unconfirmed domains and structural gaps |

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

Key thresholds defined in `prompt_architect.py`:

| Constant | Default | Description |
|---|---|---|
| `MIN_FUNCTIONAL_REQS` | 10 | Minimum functional requirements before Phase 3 NFR probing begins |
| `MIN_NFR_PER_CATEGORY` | 2 | Minimum measurable requirements per mandatory NFR category |

Domain gate re-seeding turns are defined in `domain_discovery.py`:

| Constant | Value | Description |
|---|---|---|
| `RESEED_TURN` | 10 | First re-seeding pass |
| `SECOND_RESEED_TURN` | 20 | Second re-seeding pass |

Session logs are written to `logs/session_<id>.json`. Generated SRS files are written to `output/SRS_<id>_<timestamp>.md`. Both directories are created automatically.

---

## Known Limitations

- **Session persistence:** Sessions are stored in memory only. Restarting the server loses all active sessions.
- **LLM call volume:** Multiple LLM calls are made per turn — domain matching (one per extracted requirement), NFR classification, sub-dimension classification, SMART batch check, and optionally decomposition and probe question generation. High-latency providers will cause noticeable turn delays.
- **Proactive question generator disabled:** `question_generator.py` exists and is functional but is commented out in `conversation_manager.py`. Gap guidance is delivered exclusively via the system prompt context block instead.
- **Domain gate seeding quality:** Seed accuracy depends on the richness of the first user message. Vague opening messages may yield a generic or incomplete domain list. Re-seeding at turns 10 and 20 partially compensates.
- **SMART heuristics:** The heuristic check in `srs_template.py` uses lightweight keyword and regex patterns. The LLM-based batch check in `conversation_manager.py` supersedes it for all actively extracted requirements, but requirements added via decomposition rely on the heuristic only.
- **Requirement extraction reliability:** The extractor depends on the LLM consistently emitting well-formed `<REQ>` and `<SECTION>` tags. Malformed or missing tags trigger weaker fallback patterns.
- **High-risk section stubs:** Hardware interfaces, logical database requirements, and design constraints are always stubbed and require manual completion by a system architect before the SRS can be used for development.
- **Single-user, no authentication:** Not intended for multi-user or production deployment.

---

*RE Assistant — Iteration 4 | University of Hildesheim*