# LLM-Based Requirements Engineering Assistant — Iteration 4

**University of Hildesheim · DSR Project**

---

## Overview

Iteration 4 addresses a root-cause finding from the Iteration-3 post-mortem: **37% average SRS completeness** despite high IEEE-830 keyword coverage. The problem was that the assistant recorded only what users explicitly volunteered, leaving entire functional domains unprobed. Iteration 4 introduces a **Domain Coverage Gate** as the primary completeness signal, replacing keyword counting as the gating mechanism for SRS generation.

| Issue                           | Iteration 3 Problem                                                                                                                      | Iteration 4 Fix                                                                                                                                                        |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Missing Functional Domains**  | Entire feature areas (e.g., appliance control, scheduling) were never surfaced because the assistant waited for the user to mention them | `DOMAIN_COVERAGE_GATE` — 8 canonical domains the session must explicitly CONFIRM or EXCLUDE before SRS generation is allowed (Priority 1)                              |
| **Silent Scope Reduction**      | When a user said "I just want to know what's going on", the assistant silently dropped all actuation requirements                        | RULE 8 forces the assistant to confirm whether a downscoped feature is permanently excluded or deferred (Priority 2)                                                   |
| **Context-Blind Domain Probes** | The system had no concept of functional domain coverage — follow-up questions targeted IEEE-830 structural gaps only                     | Domain-first priority pass in `ProactiveQuestionGenerator` (IT4-A): unprobed domains are always addressed before NFR or structural gaps (Priority 3)                   |
| **False Functional Coverage**   | FR count ≥ 3 could mark functional coverage as "covered" even when whole domains had never been discussed                                | Domain gate check integrated into `_classify_functional_coverage()` (IT4-G3): functional remains at most "partial" while any domain is UNPROBED                        |
| **Single Completeness Metric**  | The UI and logs showed only IEEE-830 percentage, which could reach 80%+ while SRS completeness was 37%                                   | Dual metrics: **Domain Completeness Score N/8** (new, primary gate) + **IEEE-830 Elicitation Coverage N/12** (retained) shown in context block every turn (Priority 5) |

The system continues to run as a **Flask web application** with a single-page HTML/JS UI.

---

## What's New in Iteration 4

### Priority 1 — Domain Coverage Gate (`prompt_architect.py`)

`DOMAIN_COVERAGE_GATE` defines 8 canonical functional domains that any elicitation session must explicitly address. Each domain carries detection keywords, exclusion keywords, and a plain-language fallback probe question.

The 8 domains are:

| Domain Key              | Label                                               |
| ----------------------- | --------------------------------------------------- |
| `climate_control`       | Climate Control (temperature & humidity)            |
| `security_alarm`        | Security & Alarm System (doors, windows, intrusion) |
| `appliance_lighting`    | Appliance & Lighting Control                        |
| `scheduling_planning`   | Scheduling & Automation Plans                       |
| `remote_access`         | Remote Access & Mobile Interface                    |
| `notifications_alerts`  | Notifications & Alerts                              |
| `user_management`       | User Management & Access Control                    |
| `hardware_connectivity` | Hardware & Connectivity Infrastructure              |

Each domain's status is computed from the conversation corpus every turn and is one of: `CONFIRMED`, `PARTIAL`, `UNPROBED`, or `EXCLUDED`. **SRS generation is blocked until all 8 domains are CONFIRMED or EXCLUDED.**

The domain gate is prominently displayed in the context block every turn:

```
━━━ DOMAIN COVERAGE GATE  [5/8 — 62%] ━━━
  ✅  Climate Control (temperature & humidity)
  ✅  Security & Alarm System
  🔶  Appliance & Lighting Control
      ↳ Probe: "You mentioned worrying about lights being left on — ..."
  ⬜  Scheduling & Automation Plans
      ↳ Probe: "Do you ever want the system to follow a routine automatically — ..."
  ...
⚠️  GATE NOT SATISFIED — Do NOT offer SRS generation yet.
NEXT ACTION: Ask about → Scheduling & Automation Plans
USE THIS PROBE: "Do you ever want the system to follow a routine automatically — ..."
```

The `PromptArchitect.is_srs_generation_permitted()` method enforces a hard three-way gate: domain gate satisfied **AND** all mandatory NFR categories covered **AND** minimum FR count met.

### Priority 2 — Scope Reduction Handling (RULE 8, `prompt_architect.py`)

RULE 8 is added to the `TASK_BLOCK`. When the user's statement implies they do not want a feature, the assistant must explicitly ask whether it should be documented as out-of-scope with a constraint tag, or simply deferred. Silent removal of requirements from scope is no longer permitted.

### Priority 3 — Mandatory Domain Probe Questions (`question_generator.py`)

`ProactiveQuestionGenerator` gains a **domain-first priority pass** (IT4-A). Before targeting any IEEE-830 structural gap, the generator checks whether any domain gate entry is UNPROBED. If so, a domain probe question is generated and returned ahead of all other follow-up questions.

Domain probe templates are added to `FALLBACK_TEMPLATES` under `domain_<key>` prefixes (IT4-B), with wording kept in sync with `DOMAIN_COVERAGE_GATE.fallback_probe`. The LLM meta-prompt is also extended with the list of unprobed domains so that LLM-generated questions can target them precisely (IT4-D).

A new `scope_reduction` template category (IT4-C) surfaces the RULE 8 confirmation question when the gap detector signals a scope reduction event.

### Priority 4 — Design-Derived Placeholder Injection (`srs_formatter.py`)

`SRSFormatter` reads the domain gate status from `PromptArchitect.compute_domain_gate_status()` and injects `[D — architecture review required]` stubs for any domain that was never confirmed or excluded. This ensures the generated SRS always contains placeholder sections for every functional domain rather than silently omitting them.

### Priority 5 — Dual Metrics (`prompt_architect.py`, `conversation_state.py`, `app.py`)

Every turn's context block now shows two separate completeness scores side by side:

- **Domain Completeness Score N/8** — the new primary completeness signal. Counts how many of the 8 canonical domains are CONFIRMED or EXCLUDED.
- **IEEE-830 Elicitation Coverage N/12** — the existing keyword-based metric, unchanged.

The `/api/session/turn` response now includes a `coverage_report` field with both metrics and the full domain gate status, alongside the existing `coverage_pct` field.

`ConversationState` gains two supporting additions:

- **IT4-S1** — `get_coverage_report()` now includes `domain_gate_status` and `domain_completeness_score` keys.
- **IT4-S2** — `is_ready_for_srs()` helper method wraps `PromptArchitect.is_srs_generation_permitted()` so `ConversationManager` has a single API call to determine readiness. The `/api/session/turn` response exposes this as the `srs_ready` boolean field.

### Gap Detector Integration (`gap_detector.py`)

Three additions integrate the domain gate into the gap detection pipeline:

- **IT4-G1 — Domain gate gap injection.** `GapDetector.analyse()` calls `compute_domain_gate()` after the IEEE-830 checklist scan and synthesises UNPROBED or PARTIAL domains as CRITICAL `CategoryGap` entries with the `domain_` prefix. This gives the question generator matching gap objects to work from even when keyword scanning would miss them.
- **IT4-G2 — Interfaces gap cross-check.** The `interfaces` coverage check now also tests against the `hardware_connectivity` domain gate entry, since the most common cause of an empty External Interfaces section was that hardware questions were never asked.
- **IT4-G3 — Functional coverage domain gate check.** `_classify_functional_coverage()` now validates both FR count and domain gate completeness. Even with FR count ≥ 3, the functional category is classified as at most "partial" if any domain remains UNPROBED.

---

## Architecture

```
app.py                              ← Flask REST API + HTML/JS UI
src/components/
├── conversation_manager.py         ← Session orchestration, LLM providers, turn loop
├── conversation_state.py           ← Session state, requirement store, coverage tracking
├── prompt_architect.py             ← 4-block dynamic prompt + Domain Coverage Gate
├── gap_detector.py                 ← IEEE-830/Volere checklist + domain gate gap injection
├── question_generator.py           ← Domain-first proactive question generation
├── requirement_extractor.py        ← Multi-strategy requirement extraction from responses
├── srs_template.py                 ← IEEE-830 data model, progressively populated
└── srs_formatter.py                ← Renders SRSTemplate to Markdown / plain text / JSON
output/                             ← Generated SRS documents (.md)
logs/                               ← JSON session logs (per-session, per-turn gap reports)
```

### System Prompt Structure (Iteration 4)

The prompt is built from four ordered blocks by `PromptArchitect.build_system_message()`:

```
[ROLE]          — active elicitation philosophy + persona
[CONTEXT]       — live state + domain gate (8-domain grid) + dual metrics (dynamic)
[GAP DIRECTIVE] — targeted follow-up from GapDetector (one-shot, cleared after use)
[TASK]          — phase-gated rules + domain gate closure checklist + RULE 8
```

### Request Lifecycle (per turn)

```
Browser POST /api/session/turn
    ↓
ConversationManager.send_turn()
    1. Build system message  (domain gate + dual metrics + gap directive from previous turn)
    2. Call LLM with full history
    3. Update ConversationState (heuristic coverage scan)
    4. Extract requirements via RequirementExtractor → commit → sync SRS template
    5. GapDetector.analyse(state)  → GapReport  (incl. IT4-G1 domain gate gaps)
    6. ProactiveQuestionGenerator.generate(gap_report, state) → QuestionSet
       → Domain-first pass (IT4-A): UNPROBED domains probed before IEEE-830 gaps
    7. PromptArchitect.extra_context ← injection text for NEXT turn
    8. Log turn + gap report to JSON
    ↓
JSON response: {
    assistant_reply, gap_report, follow_up_questions,
    coverage_pct, coverage_report,   ← dual metrics + domain gate status
    srs_ready                         ← hard domain gate check
}
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

Each `/api/session/turn` response now includes:

- `assistant_reply` — the LLM's response
- `gap_report` — full post-turn gap analysis (including injected domain gate gaps)
- `follow_up_questions` — domain-first proactive questions (for UI display)
- `coverage_pct` — current IEEE-830 coverage percentage
- `coverage_report` — **new**: domain gate status + domain completeness score + IEEE-830 score
- `srs_ready` — **new**: boolean hard gate check (domain gate + NFRs + FR count)

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
├── output/                         # Generated SRS files
└── logs/                           # Session logs (JSON)
```

---

## Installation & Running

### Prerequisites

```bash
pip install flask flask-cors requests
# For OpenAI provider:
pip install openai
```

### Environment Variables

```bash
# OpenAI
export OPENAI_API_KEY=sk-...

# Ollama (Hildesheim server)
export OLLAMA_API_KEY=...
export OLLAMA_BASE_URL=https://genai-01.uni-hildesheim.de/ollama   # optional
```

### Starting the Server

```bash
# Stub provider (no API key required — for UI testing)
python app.py --provider stub

# OpenAI GPT-4o
python app.py --provider openai --model gpt-4o

# Ollama (Hildesheim)
python app.py --provider ollama --model llama3.1:8b

# Custom host/port
python app.py --provider openai --host 0.0.0.0 --port 8080
```

Open `http://localhost:5000` in a browser to use the UI.

### Generating the SRS

Trigger SRS generation with any of:

- Phrases such as `generate srs`, `I'm done`, `end session`, `export srs`
- The **Generate SRS** button in the UI
- Automatic closure once the domain gate is satisfied, all mandatory NFR categories are covered, and the minimum FR count (≥ 5) is met

The SRS is saved to `output/` and available for download via the UI or the `/api/session/download_srs` endpoint.

---

## Gap Detection: IEEE-830 Coverage Checklist

The `GapDetector` tracks 19 categories across three severity levels. In addition to the checklist scan, domain gate gaps are synthesised as CRITICAL entries when any of the 8 domains is UNPROBED (IT4-G1).

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

## Domain Coverage Gate: SRS Generation Readiness

SRS generation is blocked until all three conditions are met:

1. **Domain gate satisfied** — all 8 domains are CONFIRMED or EXCLUDED
2. **All 6 mandatory NFR categories covered** — performance, usability, security_privacy, reliability, compatibility, maintainability
3. **Minimum FR count reached** — ≥ 5 functional requirements extracted

The gate status is visible in the UI coverage panel and is returned in every `/api/session/turn` response as `srs_ready`.

---

## Ablation Study Support

Iteration 4 retains the ablation study flag from Iteration 3:

```bash
# Gap detection ON (default)
python app.py --provider ollama

# Gap detection OFF — pass gap_detection=false in the /api/session/start body
curl -X POST http://localhost:5000/api/session/start \
     -H "Content-Type: application/json" \
     -d '{"gap_detection": false}'
```

When `gap_detection=false`, `GapDetector` returns a fully-covered dummy report, domain gate injection is bypassed, no questions are generated, and no directive is injected into the prompt. All other behaviour is identical, isolating the effect of the gap detection and domain coverage components.

Session logs record `gap_detection_enabled` at session start and include the full `GapReport` (including domain gate status) per turn.

---

## Output Files

### SRS Document (`output/srs_<session_id>.md`)

A full IEEE 830-1998 compliant specification including:

- §1 Introduction (purpose, scope, definitions, overview)
- §2 Overall Description (product perspective, functions, user characteristics, constraints, assumptions)
- §3 Specific Requirements (functional, interface, performance, reliability, security, maintainability, compatibility, usability)
- Appendix A: Traceability Matrix (req_id → section → source turn → SMART score)
- Appendix B: Coverage & Quality Report (including domain completeness score)
- Appendix C: Conversation Transcript Summary

Uncovered domains receive `[D — architecture review required]` stubs injected by `SRSFormatter` (Priority 4). Each requirement is annotated with a SMART quality badge and a priority indicator (🔴 Must-have / 🟡 Should-have / 🟢 Nice-to-have).

### Session Log (`logs/session_<session_id>.json`)

A structured JSON log including per-turn gap reports and domain gate status. Each turn entry contains:

- `turn_id`, `user_message`, `assistant_message`
- `categories_updated` — IEEE-830 categories touched this turn
- `gap_report` — full `GapReport` snapshot (IEEE-830 gaps + synthesised domain gate gaps)

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
The conversation was too short or did not contain clear requirement statements. The coverage panel shows both the domain gate status and IEEE-830 scores — address any UNPROBED domains and uncovered NFR categories before generating the SRS.

**`srs_ready` stays `false` after many turns**
Check the domain gate status in the coverage panel. The most common cause is one or more domains remaining UNPROBED. The assistant will surface probe questions automatically, but you can also ask directly about the indicated domain.

**Gap report shows 0% coverage after several turns**
Check that `gap_detection` was not set to `false` when the session was started. Confirm via `GET /api/session/status`.

**Port already in use**

```bash
python app.py --port 5001
```

---

## Research Foundation

Iteration 4 directly addresses the 37% average SRS completeness finding from the Iteration-3 evaluation:

- **Domain Coverage Gate** ensures that functional domains are exhaustively surfaced, not just recorded when volunteered
- **Domain-first question priority** guarantees that structural domain gaps are addressed before NFR or stylistic gaps
- **Dual completeness metrics** expose the divergence between keyword-based coverage (which can be misleadingly high) and actual domain coverage
- **RULE 8 scope reduction handling** prevents silent requirement loss when users use preference language rather than out-of-scope language
- **Design-derived SRS stubs** ensure the generated document always acknowledges uncovered domains rather than omitting them

---

## License

Academic Research Project — University of Hildesheim

Team members: Hunain Murtaza (1750471) · David Tashjian (1750243) · Saad Younas (1750124) · Amine Rafai (1749821) · Khaled Shaban (1750283) · Mohammad Alsaiad (1750755)
