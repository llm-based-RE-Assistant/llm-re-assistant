# LLM-Based Requirements Engineering Assistant — Iteration 2

**University of Hildesheim · DSR Project**

---

## Overview

Iteration 2 is a complete redesign of the RE Assistant, addressing three systemic failure modes identified during Iteration 1 evaluation:

| Failure Mode                          | Iteration 1 Problem                                                                                     | Iteration 2 Fix                                                                                                                  |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **FM-1: Ambiguity Acceptance**        | Vague terms ("fast", "secure", "simple") were recorded verbatim into the SRS without challenge          | Ambiguity Challenge Rule: the assistant must demand measurable operationalisation before accepting any vague qualifier           |
| **FM-2: Privacy/Security Blind Spot** | NFR categories — especially Security & Privacy — were routinely skipped                                 | Mandatory NFR Coverage Checklist: 6 NFR categories must be addressed before SRS generation is permitted                          |
| **FM-3: Premature Closure**           | The assistant used a fixed 3-turn template and generated the SRS before sufficient coverage was reached | Dynamic conversation state injected into every system prompt, blocking SRS generation until all mandatory categories are covered |

The system now runs as a **Streamlit web application** (replacing the previous Flask + CLI interface) and supports multiple LLM backends.

---

## What's New in Iteration 2

### Architecture

Iteration 2 introduces a fully modular component architecture. Every component has a single responsibility and is independently testable:

```
app.py                          ← Streamlit UI entry point
src/components/
├── prompt_architect.py         ← Modular 3-block system prompt builder
├── conversation_state.py       ← Session state, requirement store, coverage tracking
├── conversation_manager.py     ← Conversation loop, LLM providers, session logger
├── srs_template.py             ← IEEE-830 data model, progressively populated
└── srs_formatter.py            ← Renders SRSTemplate to Markdown / plain text / JSON
output/                         ← Generated SRS documents (.md)
logs/                           ← JSON session logs for evaluation traceability
```

### Modular Prompt Architecture (`prompt_architect.py`)

The system prompt is built from three independently-replaceable blocks on every turn:

- **ROLE block** (static): Expert RE persona with 15 years of experience, IEEE-830 and SMART criteria expertise
- **CONTEXT block** (dynamic): Current session state — which IEEE-830 categories are covered vs. missing, requirements elicited so far, mandatory NFR alert if categories remain unaddressed
- **TASK block** (static): Six hard behavioural rules covering ambiguity challenge, NFR coverage, multi-turn elicitation, conflict detection, requirement formalisation, and closure conditions

This design supports ablation studies: any block can be replaced or disabled without touching the others.

### Conversation State Management (`conversation_state.py`)

`ConversationState` is the single source of truth for the session, tracking:

- All 12 IEEE-830 categories with per-category coverage status (`NOT_STARTED`, `PARTIALLY_COVERED`, `COVERED`)
- A structured requirement store keyed by ID (`FR-001`, `NFR-001`, `CON-001`) with deduplication
- Full turn history (user + assistant messages) for context window management
- A two-layer coverage detection strategy: lightweight keyword heuristics run on every turn, plus explicit `mark_category_covered()` calls from the manager
- The 6 mandatory NFR categories that gate SRS generation

### LLM Provider Abstraction (`conversation_manager.py`)

The `LLMProvider` abstract interface allows swapping backends without any other code changes:

- **`OllamaProvider`**: Connects to the University of Hildesheim Ollama server (`genai-01.uni-hildesheim.de/ollama`). Requires `OLLAMA_API_KEY` and optionally `OLLAMA_BASE_URL`.
- **`OpenAIProvider`**: GPT-4o via the OpenAI Python SDK. Requires `OPENAI_API_KEY`.
- **`StubProvider`**: Scripted deterministic responses for UI testing without a live LLM.

All providers are configured from the Streamlit sidebar at session start, requiring no code changes between providers.

The `ConversationManager` orchestrates the session loop. On every turn it: builds the dynamic system message, assembles the full message history, calls the LLM, updates conversation state, syncs the SRS template, and logs the turn to JSON. Temperature is fixed at `0.0` for reproducible evaluation runs.

### SRS Generation Pipeline

SRS generation is a two-stage process triggered either by explicit user command or automatic detection of full mandatory coverage:

1. **LLM Extraction**: The full conversation transcript is sent to the LLM in a single structured prompt. The model extracts all requirements as JSON, converting natural language into IEEE "shall" form, distinguishing user statements from assistant questions, and assigning each requirement to its correct IEEE-830 category.
2. **Template + Formatter render**: The extracted requirements populate `SRSTemplate`, which mirrors the IEEE 830-1998 section hierarchy exactly (§1–§4). `SRSFormatter` renders the populated template to a Markdown document including SMART quality badges per requirement, an open-issues block for unresolved ambiguities, and three appendices: Traceability Matrix, Coverage & Quality Report, and Conversation Transcript Summary.

### Streamlit UI (`app.py`)

The UI provides exactly three features:

1. **Chat interface**: Multi-turn elicitation conversation with the RE Assistant
2. **Coverage panel**: Live IEEE-830 coverage tracker in the sidebar, updated after every turn, showing covered/missing categories with mandatory NFR highlighting
3. **Generate SRS**: One-click download of the generated `.md` SRS document

The interface is designed as a clean academic tool. It uses IBM Plex Sans and IBM Plex Mono fonts and a dark panel aesthetic. All Streamlit chrome (menu, header, footer) is hidden.

---

## Directory Structure

```
re-assistant/
├── app.py                          # Streamlit application entry point
├── requirements.txt                # Python dependencies
├── .env                            # API keys (not committed to version control)
├── src/
│   └── components/
│       ├── prompt_architect.py     # 3-block prompt builder, IEEE-830 registry
│       ├── conversation_state.py   # Session state, requirement store
│       ├── conversation_manager.py # Conversation loop, providers, logger
│       ├── srs_template.py         # IEEE-830 data model
│       └── srs_formatter.py        # Markdown/JSON/plain-text renderer
├── output/                         # Generated SRS documents (auto-created)
└── logs/                           # JSON session logs (auto-created)
```

---

## Prerequisites

- Python 3.10 or higher
- An LLM backend: Ollama (local/university server), OpenAI API access, or the built-in Stub provider for testing

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

Neither key is required if using the Stub provider for UI testing.

---

## Running the Application

```bash
streamlit run app.py
```

The application opens at `http://localhost:8501`.

You can also pass provider and model as command-line arguments:

```bash
streamlit run app.py -- --provider ollama --model gemma3:latest
streamlit run app.py -- --provider openai --model gpt-4o
streamlit run app.py -- --provider stub
```

---

## Using the Application

### Starting a session

1. On the landing screen, select your LLM provider and model.
2. Click **▶ Start Session**.
3. Describe the software system you want to specify. The assistant will ask structured follow-up questions.

### During elicitation

- The **Coverage Panel** in the left sidebar shows live IEEE-830 category coverage. Mandatory NFR categories are highlighted in bold. The progress bar reflects overall coverage percentage.
- The assistant will not accept vague qualifiers. If you say "it should be fast", it will ask for a measurable target before proceeding.
- Session metrics (turns, functional requirements, NFRs) update in real time.

### Generating the SRS

The SRS can be triggered in three ways:

- Type a phrase such as `generate srs`, `I'm done`, or `end session`
- Click the **📄 Generate SRS** button at any time
- The session closes automatically once all 6 mandatory NFR categories are covered and at least one functional requirement has been recorded (minimum 3 turns)

If mandatory NFR categories were not fully elicited, the SRS is still generated with `NOT ELICITED` placeholders in the relevant sections, and a warning is displayed.

After generation, the SRS can be downloaded as a `.md` file or previewed in the chat. The file is also saved to `output/`.

### Starting a new session

Click **🔄 Start new session** to reset the conversation and begin a new project. All session logs are preserved in `logs/`.

---

## Output Files

### SRS Document (`output/srs_<session_id>.md`)

A full IEEE 830-1998 compliant specification including:

- §1 Introduction (purpose, scope, definitions, overview)
- §2 Overall Description (product perspective, functions, user characteristics, constraints, assumptions)
- §3 Specific Requirements (functional requirements, interface requirements, performance, reliability, security, maintainability, compatibility, usability)
- Appendix A: Traceability Matrix (req_id → section → source turn → SMART score)
- Appendix B: Coverage & Quality Report
- Appendix C: Conversation Transcript Summary

Each requirement is annotated with a SMART quality badge (★☆☆ 1/5 to ★★★ 5/5) and a priority indicator (🔴 Must-have / 🟡 Should-have / 🟢 Nice-to-have).

### Session Log (`logs/session_<session_id>.json`)

A structured JSON log of every turn, including timestamps, categories updated per turn, requirements added per turn, and a final coverage report. Used for evaluation and traceability.

---

## IEEE-830 Category Coverage

The system tracks 12 categories. The 6 marked **mandatory** must be addressed before the SRS can be generated.

| Category                                 | Mandatory |
| ---------------------------------------- | --------- |
| System Purpose & Goals                   |           |
| System Scope & Boundaries                |           |
| Stakeholders & User Classes              |           |
| Functional Requirements                  |           |
| Performance Requirements                 | ✓         |
| Usability Requirements                   | ✓         |
| Security & Privacy Requirements          | ✓         |
| Reliability & Availability Requirements  | ✓         |
| Compatibility & Portability Requirements | ✓         |
| Maintainability Requirements             | ✓         |
| Design & Implementation Constraints      |           |
| External Interfaces                      |           |

---

## Configuration Reference

| Environment Variable | Provider | Description                                                     |
| -------------------- | -------- | --------------------------------------------------------------- |
| `OLLAMA_API_KEY`     | Ollama   | Bearer token for the Ollama server                              |
| `OLLAMA_BASE_URL`    | Ollama   | Base URL (default: `https://genai-01.uni-hildesheim.de/ollama`) |
| `OPENAI_API_KEY`     | OpenAI   | OpenAI API key                                                  |

LLM temperature is fixed at `0.0` across all providers for reproducible evaluation runs.

---

## Troubleshooting

**Ollama connection error**
Verify that `OLLAMA_API_KEY` is set correctly in `.env` and that the university VPN is active if required.

**OpenAI authentication error**
Verify that `OPENAI_API_KEY` is set and has sufficient quota. The default model is `gpt-4o`.

**SRS contains only `NOT ELICITED` placeholders**
The LLM extraction step found no extractable requirements. This can happen if the conversation was very short or the transcript did not contain clear requirement statements. Conduct a longer elicitation session before generating the SRS.

**Port already in use**
Streamlit defaults to port 8501. Run on a different port with:

```bash
streamlit run app.py --server.port 8502
```

---

## Research Foundation

This iteration addresses findings from the Iteration 1 evaluation:

- **Modular prompt architecture**: supports ablation testing of individual prompt blocks
- **Dynamic state injection**: prevents premature closure (see Failure Mode 3)
- **Mandatory NFR checklist**: prevents security/privacy blind spots (see Failure Mode 2)
- **Ambiguity challenge rule**: enforces SMART requirement quality (see Failure Mode 1)
- **LLM-based requirement extraction**: improves fidelity of elicited content over heuristic scanning

---

## License

Academic Research Project — University of Hildesheim

Team members: Hunain Murtaza (1750471) · David Tashjian (1750243) · Saad Younas (1750124) · Amine Rafai (1749821) · Khaled Shaban (1750283) · Mohammad Alsaiad (1750755)
