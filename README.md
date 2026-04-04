# LLM-Based Requirements Engineering Assistant — Iteration 3

**University of Hildesheim · DSR Project**

---

## Overview

Iteration 3 builds on Iteration 2's modular architecture and addresses three new systemic gaps identified during Iteration 2 evaluation:

| Issue                         | Iteration 2 Problem                                                                                                       | Iteration 3 Fix                                                                                                                                       |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Gap Detection Not Wired**   | `GapDetector` and `ProactiveQuestionGenerator` were implemented but never called in the conversation loop                 | Both components are now fully wired into `send_turn()`. Gap analysis runs after every turn; results are injected into the next system prompt (FIX-W1) |
| **Template-Blind Questions**  | Follow-up questions were generated from static templates, ignoring what the user just said                                | Primary question mode is now LLM-generated via a meta-prompt with full conversation context (FIX-B); templates are retained as a graceful fallback    |
| **False Functional Coverage** | Gap detector reported functional coverage based on keyword counts alone, triggering too early before any real FRs existed | Functional coverage is now validated directly against the requirement store (`functional_count`), not keywords (FIX-G1/G2)                            |

The system continues to run as a **Flask web application** with a single-page HTML/JS UI.

---

## What's New in Iteration 3

### Gap Detection Pipeline (`gap_detector.py`)

The `GapDetector` component analyses `ConversationState` after every turn and produces a structured `GapReport`. Key changes:

- **FIX-G1/G2 — Functional coverage uses the requirement store.** Coverage is now based on `state.functional_count` (≥3 FRs → covered; ≥1 → partial; 0 → uncovered). Keyword counting alone is no longer sufficient to mark functional requirements as covered.
- **FIX-G3 — Raised keyword thresholds.** CRITICAL categories require ≥4 distinct keyword hits (was 3). This reduces false positives in early turns where generic words like "allow" or "must" appear in unrelated discussion.
- **FIX-G4 — Expanded checklist.** Added `scalability`, `data_requirements`, `testability`, `deployment`, `use_cases`, `business_rules`, and `assumptions` to the checklist. These categories had question templates in Iteration 2 but were invisible to the detector, meaning gaps were never surfaced.
- **Ablation support.** `GapDetector(enabled=False)` returns a fully-covered dummy report, allowing controlled ablation study runs where gap detection is disabled.

The unified coverage checklist maps each category to its IEEE 830-1998 and Volere reference, a severity level (`CRITICAL`, `IMPORTANT`, `OPTIONAL`), and detection keywords.

### Proactive Question Generator (`question_generator.py`)

- **FIX-A — Templates removed as primary source.** Hard-coded template questions were context-blind: they told the LLM what to ask regardless of what the user had just said, producing robotic follow-ups and shorter user responses.
- **FIX-B — LLM-generated questions (primary).** `ProactiveQuestionGenerator` now calls the LLM with a meta-prompt containing the last 4 turns of conversation, project name, FR/NFR counts, and the gap category to probe. The result is a single, targeted, context-aware question that feels like a natural continuation of the conversation.
- **FIX-C — Templates kept as fallback.** If no LLM provider is available (unit tests, offline mode) or the meta-call fails, the generator falls back to parameterised templates. This preserves backward-compatibility and ablation study support.
- **FIX-D — FR-aware priority.** When `functional_count < 3`, the generator always targets the functional gap first, overriding the normal `CRITICAL → IMPORTANT → OPTIONAL` ordering.
- **`QuestionTracker`** prevents the same category from being probed more than 3 times per session.

### Conversation Manager Wiring (`conversation_manager.py`)

- **FIX-W1 — Full pipeline wired.** `send_turn()` now runs the complete gap → question → inject pipeline on every turn. Previously, both components were instantiated but `analyse()` and `generate()` were never called.
- **FIX-W2 — Per-session `QuestionTracker`.** A fresh `QuestionTracker` is created in `start_session()` and carried throughout the session.
- **FIX-W3 — Shared LLM provider.** `ProactiveQuestionGenerator` is initialised with the same `LLMProvider` instance as the main loop, enabling mode `"llm"` for context-aware question generation.
- **FIX-W4 — Correct injection timing.** The gap directive is written to `self._architect.extra_context` _after_ the current turn's state update, so the _next_ turn's system message receives the fresh directive — not a stale one from the previous turn. This matches the one-shot injection design in `PromptArchitect`.

### Requirement Extractor (`requirement_extractor.py`)

The extractor uses a three-strategy cascade to capture requirements from LLM responses:

1. **Primary — `<REQ>` tags (multi-line).** The LLM is instructed to wrap every formalised requirement in `<REQ type="..." category="...">...</REQ>` delimiters. This reliably captures multi-line requirements with bullet sub-items intact. It was introduced to fix a bug where single-line regex patterns captured only the first line of a multi-line requirement (e.g. a reminder schedule with sub-items).
2. **Fallback 1 — Numbered pattern.** `Requirement N (Type): ...` format for backward-compatibility.
3. **Fallback 2 — "Shall" sentences.** `The system shall ...` as last resort.

All extracted requirements are committed to `ConversationState` with deduplication and the SRS template is synced on every turn.

---

## Architecture

```
app.py                              ← Flask REST API + HTML/JS UI
src/components/
├── conversation_manager.py         ← Session orchestration, LLM providers, turn loop
├── conversation_state.py           ← Session state, requirement store, coverage tracking
├── prompt_architect.py             ← 3-block dynamic system prompt builder
├── gap_detector.py                 ← IEEE-830/Volere coverage checklist + gap analysis
├── question_generator.py           ← LLM-generated proactive follow-up questions
├── requirement_extractor.py        ← Multi-strategy requirement extraction from responses
├── srs_template.py                 ← IEEE-830 data model, progressively populated
└── srs_formatter.py                ← Renders SRSTemplate to Markdown / plain text / JSON
output/                             ← Generated SRS documents (.md)
logs/                               ← JSON session logs (per-session, per-turn gap reports)
```

### Request Lifecycle (per turn)

```
Browser POST /api/session/turn
    ↓
ConversationManager.send_turn()
    1. Build system message  (includes gap directive from previous turn)
    2. Call LLM with full history
    3. Update ConversationState (heuristic coverage scan)
    4. Extract requirements via RequirementExtractor → commit → sync SRS template
    5. GapDetector.analyse(state)  → GapReport
    6. ProactiveQuestionGenerator.generate(gap_report, state, tracker) → QuestionSet
    7. PromptArchitect.extra_context ← injection text for NEXT turn
    8. Log turn + gap report to JSON
    ↓
JSON response: { assistant_reply, gap_report, follow_up_questions, coverage_pct }
```

---

## REST API

| Method | Endpoint                    | Description                                                 |
| ------ | --------------------------- | ----------------------------------------------------------- |
| POST   | `/api/session/start`        | Start a new session. Body: `{ "gap_detection": true }`      |
| POST   | `/api/session/turn`         | Send a user message. Body: `{ "session_id", "message" }`    |
| GET    | `/api/session/status`       | Coverage report + gap report. Query: `?session_id=...`      |
| POST   | `/api/session/generate_srs` | Finalise session and generate SRS. Body: `{ "session_id" }` |
| GET    | `/api/session/download_srs` | Download the generated SRS file. Query: `?session_id=...`   |
| GET    | `/api/health`               | Health check.                                               |

Each `/api/session/turn` response includes:

- `assistant_reply` — the LLM's response
- `gap_report` — full post-turn gap analysis
- `follow_up_questions` — list of proactively generated questions (for UI display)
- `coverage_pct` — current coverage percentage

---

## Directory Structure

```
re-assistant/
├── app.py                          # Flask application entry point
├── index.html                      # Single-page UI (served by Flask)
├── requirements.txt                # Python dependencies
├── .env                            # API keys (not committed to version control)
├── src/
│   └── components/
│       ├── conversation_manager.py
│       ├── conversation_state.py
│       ├── prompt_architect.py
│       ├── gap_detector.py
│       ├── question_generator.py
│       ├── requirement_extractor.py
│       ├── srs_template.py
│       └── srs_formatter.py
├── output/                         # Generated SRS documents (auto-created)
└── logs/                           # JSON session logs (auto-created)
```

---

## Prerequisites

- Python 3.10 or higher
- An LLM backend: Ollama (local/university server), OpenAI API, or the built-in Stub provider for testing

---

## Installation

### 1. Clone and enter the project directory

```bash
cd re-assistant
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv

# Linux / macOS
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```bash
# Required for Ollama (university server)
OLLAMA_API_KEY=your_ollama_api_key
OLLAMA_BASE_URL=https://genai-01.uni-hildesheim.de/ollama   # default if omitted

# Required for OpenAI
OPENAI_API_KEY=your_openai_api_key
```

Neither key is required when using the Stub provider for UI testing.

---

## Running the Application

```bash
python app.py
```

The application starts at `http://127.0.0.1:5000`.

You can pass provider, model, host, and port as arguments:

```bash
python app.py --provider ollama --model llama3.1:8b
python app.py --provider openai --model gpt-4o
python app.py --provider stub
python app.py --host 0.0.0.0 --port 8080 --debug
```

---

## Using the Application

### Starting a session

Open `http://127.0.0.1:5000` in a browser. The UI presents an opening message and begins the elicitation conversation.

### During elicitation

The assistant proactively guides the conversation using the gap detection pipeline:

- After every turn, the assistant identifies the highest-priority uncovered IEEE-830 category
- A context-aware follow-up question is generated by the LLM using the last 4 turns of conversation
- The question is injected into the next system prompt as a directive, ensuring natural integration rather than a scripted list

The assistant continues to enforce the Iteration 2 rules: ambiguity challenge (vague terms like "fast" require measurable targets), mandatory NFR coverage before SRS generation is permitted, and conflict detection.

### Generating the SRS

Trigger SRS generation with any of:

- Phrases such as `generate srs`, `I'm done`, `end session`, `export srs`
- The **Generate SRS** button in the UI
- Automatic closure once all mandatory NFR categories are covered and sufficient functional requirements have been elicited

The SRS is saved to `output/` and available for download via the UI or the `/api/session/download_srs` endpoint.

---

## Gap Detection: IEEE-830 Coverage Checklist

The `GapDetector` tracks 16 categories across three severity levels. The 6 CRITICAL NFR categories from Iteration 2 remain mandatory gates for SRS generation; the expanded checklist adds IMPORTANT and OPTIONAL categories for richer gap reporting.

| Category                            | Severity  |
| ----------------------------------- | --------- |
| System Purpose & Goals              | CRITICAL  |
| System Scope & Boundaries           | CRITICAL  |
| Stakeholders & User Classes         | CRITICAL  |
| Functional Requirements             | CRITICAL  |
| Performance Requirements            | CRITICAL  |
| Usability & Accessibility           | CRITICAL  |
| Security & Privacy Requirements     | CRITICAL  |
| Reliability & Availability          | CRITICAL  |
| Compatibility & Portability         | CRITICAL  |
| Maintainability Requirements        | CRITICAL  |
| Use Cases & User Stories            | IMPORTANT |
| Business Rules & Constraints        | IMPORTANT |
| Scalability                         | IMPORTANT |
| External Interfaces                 | IMPORTANT |
| Data Requirements                   | OPTIONAL  |
| Design & Implementation Constraints | OPTIONAL  |
| Assumptions & Dependencies          | OPTIONAL  |
| Testability                         | OPTIONAL  |
| Deployment                          | OPTIONAL  |

---

## Ablation Study Support

Iteration 3 is designed for controlled ablation experiments comparing gap-detection ON vs. OFF:

```bash
# Gap detection ON (default)
python app.py --provider ollama

# Gap detection OFF — pass gap_detection=false in the /api/session/start body
curl -X POST http://localhost:5000/api/session/start \
     -H "Content-Type: application/json" \
     -d '{"gap_detection": false}'
```

When `gap_detection=false`, `GapDetector` returns a fully-covered dummy report. The question generator is also bypassed, and no directive is injected into the prompt architect. All other behaviour is identical, isolating the effect of the gap detection component.

Session logs record `gap_detection_enabled` at session start and include the full `GapReport` per turn, providing a complete audit trail for evaluation.

---

## Output Files

### SRS Document (`output/srs_<session_id>.md`)

A full IEEE 830-1998 compliant specification including:

- §1 Introduction (purpose, scope, definitions, overview)
- §2 Overall Description (product perspective, functions, user characteristics, constraints, assumptions)
- §3 Specific Requirements (functional, interface, performance, reliability, security, maintainability, compatibility, usability)
- Appendix A: Traceability Matrix (req_id → section → source turn → SMART score)
- Appendix B: Coverage & Quality Report
- Appendix C: Conversation Transcript Summary

Each requirement is annotated with a SMART quality badge and a priority indicator (🔴 Must-have / 🟡 Should-have / 🟢 Nice-to-have).

### Session Log (`logs/session_<session_id>.json`)

A structured JSON log including per-turn gap reports. Each turn entry contains:

- `turn_id`, `user_message`, `assistant_message`
- `categories_updated` — IEEE-830 categories touched this turn
- `gap_report` — full `GapReport` snapshot after the turn (gaps by severity, coverage percentage, per-category status)

---

## LLM Providers

| Provider | Class            | Env Var          | Notes                                           |
| -------- | ---------------- | ---------------- | ----------------------------------------------- |
| `openai` | `OpenAIProvider` | `OPENAI_API_KEY` | GPT-4o by default                               |
| `ollama` | `OllamaProvider` | `OLLAMA_API_KEY` | Hildesheim server; `OLLAMA_BASE_URL` optional   |
| `stub`   | `StubProvider`   | —                | Deterministic scripted responses for UI testing |

Temperature is fixed at `0.0` for the main conversation loop for reproducible evaluation runs. The question generator meta-prompt uses `temperature=0.4` to produce varied follow-up questions across turns.

---

## Troubleshooting

**Ollama connection error**
Verify that `OLLAMA_API_KEY` is set and the university VPN is active if required.

**OpenAI authentication error**
Verify that `OPENAI_API_KEY` is set and has sufficient quota.

**SRS contains only `NOT ELICITED` placeholders**
The conversation was too short or did not contain clear requirement statements. Conduct a longer elicitation session — the coverage panel will indicate which categories still need to be addressed.

**Gap report shows 0% coverage after several turns**
Check that `gap_detection` was not set to `false` when the session was started (`/api/session/start` body). Confirm via `GET /api/session/status`.

**Port already in use**

```bash
python app.py --port 5001
```

---

## Research Foundation

Iteration 3 addresses findings from the Iteration 2 evaluation:

- **Wired gap-detection pipeline** prevents the assistant from ignoring coverage gaps it has already identified (fixes the "implemented but not called" issue)
- **LLM-generated follow-up questions** improve conversational naturalness and user response quality compared to template-driven questioning
- **Requirement-store-based functional coverage** eliminates false positive coverage signals from incidental keyword matches
- **Expanded coverage checklist** (16 categories vs. 12) surfaces gaps in use cases, business rules, scalability, and testability that were previously invisible to the detector

---

## License

Academic Research Project — University of Hildesheim

Team members: Hunain Murtaza (1750471) · David Tashjian (1750243) · Saad Younas (1750124) · Amine Rafai (1749821) · Khaled Shaban (1750283) · Mohammad Alsaiad (1750755)
