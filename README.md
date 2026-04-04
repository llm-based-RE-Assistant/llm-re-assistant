# RE Assistant — Iteration 3

### Requirements Engineering Assistant · University of Hildesheim

---

## Overview

RE Assistant is an AI-powered requirements elicitation tool that conducts structured interviews with stakeholders and produces IEEE-830-compliant Software Requirements Specifications (SRS). Iteration 3 introduces **proactive gap detection** and a **question generation pipeline** that actively identifies missing requirements and injects targeted follow-up prompts into the LLM's context window — preventing premature session closure and improving SRS completeness.

---

## What's New in Iteration 3

Iteration 3 addresses three failure modes identified in the Iteration 2 evaluation:

| Failure Mode                 | Description                                                                | Iteration 3 Fix                                                                                     |
| ---------------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| **FM-1: Silent Gaps**        | LLM would finish elicitation without covering mandatory NFR categories     | `GapDetector` runs after every turn and reports uncovered categories                                |
| **FM-2: Static Questioning** | Follow-up questions were generic templates recycled across sessions        | `ProactiveQuestionGenerator` calls the LLM with a meta-prompt to produce context-aware questions    |
| **FM-3: Premature Closure**  | Baseline offered to generate SRS after just 3 turns regardless of coverage | Phase-gated `PromptArchitect` blocks SRS generation until a checklist of 18 categories is addressed |

Two new components were added (`gap_detector.py`, `question_generator.py`) and the `PromptArchitect` and `ConversationManager` were extended to use them.

---

## Architecture

```
Browser  ←→  Flask REST API  ←→  ConversationManager
                                       │
                              ┌────────┴────────┐
                              │                 │
                        PromptArchitect    RequirementExtractor
                              │
                        ┌─────┴──────┐
                        │            │
                   GapDetector  ProactiveQuestionGenerator
                        │            │
                   GapReport    QuestionSet  ←→  QuestionTracker
                        └─────┬──────┘
                               │
                    [injected into extra_context]
                               │
                           LLM Turn
                               │
                    ConversationState (updated)
                               │
                    SRSTemplate (updated)
                               │
                    SRSFormatter → SRS .md file
```

### Component Summary

| Component                    | File                       | Responsibility                                                                              |
| ---------------------------- | -------------------------- | ------------------------------------------------------------------------------------------- |
| `ConversationManager`        | `conversation_manager.py`  | Orchestrates the full elicitation loop; coordinates all sub-components                      |
| `ConversationState`          | `conversation_state.py`    | Single source of truth: turns, requirements, coverage tracking                              |
| `PromptArchitect`            | `prompt_architect.py`      | Builds the system message from modular blocks; injects gap directives                       |
| `GapDetector`                | `gap_detector.py`          | Analyses state against an 18-category IEEE-830/Volere checklist; returns `GapReport`        |
| `ProactiveQuestionGenerator` | `question_generator.py`    | Generates one targeted follow-up question per turn via LLM meta-prompt or template fallback |
| `RequirementExtractor`       | `requirement_extractor.py` | Parses `<REQ>` tags and "shall" patterns from LLM responses into structured requirements    |
| `SRSTemplate`                | `srs_template.py`          | IEEE-830 data container; populated progressively; applies SMART heuristic scoring           |
| `SRSFormatter`               | `srs_formatter.py`         | Renders `SRSTemplate` + `ConversationState` to Markdown, plain text, or JSON                |
| `app.py`                     | `app.py`                   | Flask REST API backend; serves the web UI                                                   |
| `index.html`                 | `index.html`               | Single-page chat UI with live coverage ring, gap panel, and follow-up question panel        |

---

## Gap Detection

The `GapDetector` maintains an 18-category checklist combining IEEE-830 and Volere standards. After every conversation turn it scans the full corpus (user messages, assistant messages, and extracted requirements) and classifies each category as `covered`, `partial`, or `uncovered`.

### Coverage Checklist

| Category                          | Severity  |
| --------------------------------- | --------- |
| System Purpose & Goals            | Critical  |
| System Scope & Boundaries         | Critical  |
| Stakeholders & User Classes       | Critical  |
| Functional Requirements           | Critical  |
| Performance Requirements          | Critical  |
| Usability & Accessibility         | Critical  |
| Security & Privacy Requirements   | Critical  |
| Reliability & Availability        | Critical  |
| Use Cases & User Stories          | Important |
| Business Rules & Constraints      | Important |
| Compatibility & Portability       | Important |
| Maintainability                   | Important |
| Scalability                       | Important |
| External Interfaces               | Important |
| Data Requirements                 | Important |
| Design Constraints                | Important |
| Assumptions & Dependencies        | Optional  |
| Testability & Acceptance Criteria | Optional  |
| Deployment & Operations           | Optional  |

Coverage percentage is computed as: `(covered + 0.5 × partial) / total × 100`.

### Ablation Study Support

The gap detector can be disabled for controlled experiments:

```python
# Gap detection ON (default)
manager = ConversationManager(provider=provider, gap_enabled=True)

# Gap detection OFF (ablation baseline)
manager = ConversationManager(provider=provider, gap_enabled=False)
```

When disabled, `GapDetector.analyse()` returns a "100% covered" report and no directives are injected into the prompt.

---

## Question Generation

`ProactiveQuestionGenerator` selects the highest-priority uncovered category from the `GapReport` and generates one targeted follow-up question per turn.

### Mode Hierarchy

1. **LLM mode (default)** — calls the LLM with a meta-prompt that includes the last 4 turns of conversation history and the target gap category. Produces context-aware, project-specific questions.
2. **Template fallback** — used when the LLM provider is unavailable or the meta-call fails. Parameterised templates exist for all 19 categories.

### Injection Pattern

The generated question is injected into `PromptArchitect.extra_context` as a one-shot directive before the next LLM call. The prompt architect automatically clears the directive after each build, ensuring it is used exactly once.

```
── PROACTIVE QUESTIONING DIRECTIVE ──
Gap to probe next: Performance Requirements (severity: CRITICAL)
Why: How fast must the system respond? What load must it handle?

A context-aware question has been pre-generated for this gap:
  "Given that your users will be submitting reports during peak hours,
   what response time would be acceptable for the dashboard to reload?"

You MAY use this question verbatim or adapt it to flow naturally.
── END DIRECTIVE ──
```

---

## Prompt Architecture

The system message is composed of four modular blocks assembled fresh on every turn:

```
=== ROLE ===
Active elicitation philosophy + 15-year RE expert persona

=== CURRENT SESSION CONTEXT ===
Live state: turn count, FR/NFR counts, phase indicator,
covered/missing IEEE-830 categories, FR deficit warning,
mandatory NFR alert

=== GAP DETECTION DIRECTIVE ===          ← injected only when a gap is found
One-shot: target category + pre-generated question

=== TASK INSTRUCTIONS ===
Phase-gated structure (4 phases), 6 non-negotiable rules,
mandatory closure checklist
```

### Phase Structure

| Phase                                   | Turns        | Goal                                           |
| --------------------------------------- | ------------ | ---------------------------------------------- |
| Phase 1: Domain & Context Discovery     | 1–3          | Establish "Why" and "Who" before "What"        |
| Phase 2: Functional Requirements (IPOS) | Ongoing      | Decompose behaviours into atomic, testable FRs |
| Phase 3: Non-Functional Requirements    | After ≥5 FRs | ISO 25010 quality attributes with metrics      |
| Phase 4: Constraints & Final Validation | Closure      | Hard limits, saturation check                  |

The assistant is blocked from advancing to Phase 3 until at least 5 distinct functional requirements have been recorded. SRS generation is blocked until the mandatory closure checklist is complete.

---

## Requirement Extraction

The `RequirementExtractor` parses assistant responses for formalised requirements using three strategies in priority order:

**Strategy 1 — REQ tags (primary)**

```xml
<REQ type="functional" category="functional">
The system shall allow users to log in with email and password.
</REQ>

<REQ type="non_functional" category="performance">
The system shall respond to all dashboard requests within 2 seconds
under a load of 500 concurrent users.
</REQ>
```

**Strategy 2 — Numbered explicit pattern (fallback)**

```
Requirement 1 (Functional): The system shall...
```

**Strategy 3 — "shall" pattern (last resort)**

```
The system shall authenticate users...
```

Extracted requirements are committed to `ConversationState` and scored against SMART criteria (Specific, Measurable, Achievable, Relevant, Testable) using a heuristic checker.

---

## SRS Output

The generated SRS follows IEEE 830-1998 structure:

```
§1  Introduction
    1.1 Purpose · 1.2 Scope · 1.3 Definitions · 1.4 References · 1.5 Overview
§2  Overall Description
    2.1 Product Perspective · 2.2 Product Functions · 2.3 User Characteristics
    2.4 General Constraints · 2.5 Assumptions and Dependencies
§3  Specific Requirements
    3.1 Functional Requirements
    3.2 External Interface Requirements (User/Hardware/Software/Communication)
    3.3 Performance Requirements
    3.4 Logical Database Requirements
    3.5 Design Constraints
    3.6 Software System Attributes (Reliability/Availability/Security/
        Maintainability/Portability/Usability)
§4  Open Issues and Conflicts
Appendix A  Traceability Matrix
Appendix B  Elicitation Coverage & Quality Report
Appendix C  Conversation Transcript Summary
```

Each requirement is annotated with its SMART score (0–5), priority (Must-have / Should-have / Nice-to-have), IEEE-830 section reference, and source turn.

---

## Web UI

The single-page UI (`index.html`) provides three panels:

- **Left panel** — live IEEE-830 coverage ring with per-category status (covered / partial / uncovered), colour-coded by severity
- **Centre** — chat interface with typing indicator and session start overlay
- **Right panel** — two tabs: _Gaps_ (current `GapReport`) and _Follow-ups_ (clickable question cards that pre-fill the input)

---

## Installation & Setup

### Prerequisites

```bash
pip install flask flask-cors requests
# Plus one of:
pip install openai          # for OpenAI provider
# or ensure Ollama is running locally / on the university server
```

### Environment Variables

| Variable          | Required for    | Description                                                     |
| ----------------- | --------------- | --------------------------------------------------------------- |
| `OPENAI_API_KEY`  | OpenAI provider | Your OpenAI API key                                             |
| `OLLAMA_API_KEY`  | Ollama provider | Bearer token for the Ollama server                              |
| `OLLAMA_BASE_URL` | Ollama provider | Base URL (default: `https://genai-01.uni-hildesheim.de/ollama`) |

### Running

```bash
# With OpenAI GPT-4o (default for production)
OPENAI_API_KEY=sk-... python app.py --provider openai --model gpt-4o

# With Ollama (university server)
OLLAMA_API_KEY=... python app.py --provider ollama --model llama3.1:8b

# With stub provider (no API key needed, for UI testing)
python app.py --provider stub

# Custom host/port
python app.py --provider openai --host 0.0.0.0 --port 8080

# Debug mode
python app.py --provider stub --debug
```

Open `http://127.0.0.1:5000` in your browser.

---

## REST API

| Method | Endpoint                    | Description                                                                   |
| ------ | --------------------------- | ----------------------------------------------------------------------------- |
| `GET`  | `/api/health`               | Health check; returns provider name                                           |
| `POST` | `/api/session/start`        | Start a new session; returns `session_id` and opening message                 |
| `POST` | `/api/session/turn`         | Send user message; returns assistant reply + gap report + follow-up questions |
| `GET`  | `/api/session/status`       | Current coverage and gap report for a session                                 |
| `POST` | `/api/session/generate_srs` | Finalise session and generate SRS document                                    |
| `GET`  | `/api/session/download_srs` | Download the generated SRS `.md` file                                         |

### Example: Start Session

```json
POST /api/session/start
{ "gap_detection": true }

Response:
{
  "session_id": "a3f9c12b",
  "opening_message": "Hello! I'm your Requirements Engineering assistant...",
  "gap_detection": true,
  "provider": "openai"
}
```

### Example: Send Turn

```json
POST /api/session/turn
{ "session_id": "a3f9c12b", "message": "I want to build a task management app for remote teams." }

Response:
{
  "session_id": "a3f9c12b",
  "assistant_reply": "Great. To understand the purpose more deeply — ...",
  "turn_id": 1,
  "gap_report": { "coverage_pct": 12.5, "critical_gaps": [...], ... },
  "follow_up_questions": [{ "category_label": "Stakeholders", "question_text": "...", ... }],
  "coverage_pct": 12.5
}
```

---

## Project Structure

```
iteration-3/
├── app.py                      # Flask web server & REST API
├── index.html                  # Single-page web UI
├── conversation_manager.py     # Core orchestration loop
├── conversation_state.py       # Session state: turns, requirements, coverage
├── prompt_architect.py         # Modular system message builder
├── gap_detector.py             # IEEE-830/Volere 18-category gap analyser  ← NEW
├── question_generator.py       # LLM meta-prompt question generator        ← NEW
├── requirement_extractor.py    # <REQ> tag + pattern-based extraction
├── srs_template.py             # IEEE-830 data container with SMART scoring
├── srs_formatter.py            # Markdown/plain-text/JSON SRS renderer
├── logs/                       # Per-session JSON logs (auto-created)
└── output/                     # Generated SRS .md files (auto-created)
```

---

## Known Limitations

- **Heuristic SMART scoring** — the current SMART checker uses keyword and pattern matching. LLM-based quality assessment is planned for Iteration 4.
- **In-memory session store** — sessions are lost on server restart. Production deployment would require Redis or a database.
- **Single-file SRS output** — only Markdown output is currently supported. DOCX/PDF export is planned.
- **LLM keyword extraction** — the `RequirementExtractor` relies on the LLM correctly using `<REQ>` tags. If the LLM deviates from the format, extraction quality degrades to the regex fallbacks.

---

## Evaluation Notes (Ablation Study)

To run the ablation study comparing gap detection ON vs. OFF:

```bash
# Condition A: Gap detection ON
python app.py --provider openai

# Condition B: Gap detection OFF
# In app.py, set gap_detection_enabled = False in the start_session body,
# or pass gap_detection: false in the POST /api/session/start body.
```

Session logs in `logs/session_<id>.json` record per-turn gap reports, category updates, and extracted requirements for offline analysis.

---

## Authors

Integrated Research Project — Requirements Engineering Assistant  
Department of Computer Science · University of Hildesheim
