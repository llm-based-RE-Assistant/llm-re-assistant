# LLM-Based Requirements Engineering Assistant — Iteration 5

**University of Hildesheim · DSR Project**

---

## Overview

Iteration 5 addresses five root-cause findings from the Iteration-4 post-mortem. The primary issues were **conversation loops** (the assistant re-asking the same domain question after the user gave a short answer), **jargon leaking into probe questions** (technical label strings appearing verbatim in what was supposed to be plain-language dialogue), **NFR gating being skippable** (the SRS could be generated without all six mandatory NFR categories), **imprecise domain matching** (substring-based matching incorrectly assigned requirements to the wrong domain), and **missing IEEE-830 sections in the generated SRS** (the document reliably captured functional requirements but left structural sections empty). Iteration 5 fixes all five issues while keeping the Domain Coverage Gate introduced in Iteration 4 as the primary completeness signal.

| Issue                         | Iteration 4 Problem                                                                                                               | Iteration 5 Fix                                                                                                                                                                                                                                                        |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Conversation Loops**        | Repeated user messages triggered the same domain probe again, creating an infinite loop on short answers                          | `FIX-LOOP` in `conversation_manager.py`: Jaccard-based duplicate detection; if a user message is >80% similar to a previous turn, the current domain is force-advanced to `confirmed` and a fresh question is generated                                                |
| **Jargon in Probe Questions** | Domain labels like "Error Detection & Recovery" appeared verbatim in questions shown to non-technical stakeholders                | `FIX-JARGON` in `prompt_architect.py` and `domain_discovery.py`: a dedicated LLM prompt (`_generate_probe`) generates plain-language questions with a concrete example; jargon ban explicitly enforced via `RULE 4`                                                    |
| **NFR Gate Bypassable**       | `is_ready_for_srs()` had a code path that could return `True` before all six mandatory NFRs were covered                          | `FIX-NFR` in `conversation_state.py` and `prompt_architect.py`: `is_ready_for_srs()` now unconditionally requires `mandatory_nfrs_covered`; Phase 3 in `TASK_BLOCK` is now marked MANDATORY with a `⛔ HARD STOP` injected into the context block for each missing NFR |
| **Imprecise Domain Matching** | Substring matching assigned requirements to wrong domains (e.g., "update" matched `user_management` instead of `maintainability`) | `FIX-MATCH` in `conversation_manager.py` and `domain_discovery.py`: LLM-based matching via `match_requirement_to_domain()`; substring fallback retained in `RequirementExtractor` only as a last resort                                                                |
| **Incomplete SRS Sections**   | The generated SRS reliably captured FRs and NFRs but left §1.2, §2.x, §3.2, §3.4, §3.5 empty                                      | New `srs_coverage.py` module: triggered at finalisation, fills missing IEEE-830 sections with hallucination-risk-tiered LLM prompts (LOW / MEDIUM / HIGH); HIGH-risk sections receive formal stubs with architect checklists instead of free-form generation           |

The system continues to run as a **Flask web application** with a single-page HTML/JS UI.

---

## What's New in Iteration 5

### FIX-LOOP — Duplicate Turn Detection (`conversation_manager.py`)

A new `_message_similarity()` helper computes Jaccard similarity on word sets between the incoming user message and every previous turn. If similarity exceeds 0.8, the turn is flagged as a duplicate. The current domain's `probe_count` is checked and if it is ≥ 2, that domain's status is force-set to `confirmed` so the assistant moves to the next domain rather than looping. This prevents the most common failure mode observed in Iteration 4 evaluations where short affirmative responses ("yes", "that's right") caused indefinite re-probing of the same domain.

### FIX-JARGON — Plain-Language Probe Generation (`domain_discovery.py`, `prompt_architect.py`)

`DomainDiscovery._generate_probe()` now calls the LLM with an explicit jargon ban to produce a single plain-language question for each domain. The prompt rules are:

1. Use everyday language — no technical terms.
2. Never include the domain label string in the question.
3. Always include a concrete example from the user's own system.
4. Ask for specific numbers where relevant.
5. Produce one sentence ending in `?`.

`RULE 4` in `PromptArchitect.TASK_BLOCK` enforces the same constraint on the main conversation loop with BAD/GOOD examples:

```
BAD:  "Can you tell me about the System Maintenance Tools aspects?"
GOOD: "Who keeps the system running — like, if there's a software update
       or something breaks, should it fix itself or do you call someone?"
```

The probe depth per domain is also capped at **one follow-up** per domain (`FIX-DEPTH`) to prevent over-probing loops while still achieving depth through requirement decomposition.

### FIX-NFR — Mandatory NFR Phase (`conversation_state.py`, `prompt_architect.py`)

`ConversationState.is_ready_for_srs()` now always evaluates `mandatory_nfrs_covered` before returning `True`, regardless of the domain gate status:

```python
def is_ready_for_srs(self):
    if self.functional_count < MIN_FUNCTIONAL_REQS: return False
    if not self.mandatory_nfrs_covered: return False          # FIX-NFR
    if self.domain_gate and self.domain_gate.seeded:
        return self.domain_gate.is_satisfied
    return True
```

`PromptArchitect._build_context_block()` inserts a `⛔ HARD STOP — MANDATORY NFR MISSING` directive whenever the domain gate is satisfied but at least one of the six NFR categories has zero coverage. The directive names the next missing category and provides a plain-language probe question for it:

| NFR Category       | Plain-language probe                                                        |
| ------------------ | --------------------------------------------------------------------------- |
| Performance        | "How quickly should things respond when you tap a button?"                  |
| Usability          | "What would make it simple enough for the least technical person?"          |
| Security & Privacy | "How should people log in, and should certain features be restricted?"      |
| Reliability        | "How dependable does this need to be — is it okay if it goes down briefly?" |
| Compatibility      | "What phones, tablets, or computers does everyone use?"                     |
| Maintainability    | "Who keeps the system running after it's set up?"                           |

### FIX-MATCH — LLM-Based Domain Matching (`domain_discovery.py`, `conversation_manager.py`)

`DomainDiscovery.match_requirement_to_domain()` now sends each extracted requirement text to the LLM alongside the full domain key/label list and asks it to return the single best-matching domain key. The LLM call uses `temperature=0.0` for determinism. A partial-prefix fallback handles minor LLM formatting variations. The old substring matching in `RequirementExtractor.match_domains()` is retained only as a last resort when `domain_label` has not been set by the LLM path.

### FIX-DEDUP — Semantic Deduplication of Decomposed Requirements (`conversation_manager.py`)

Requirement decomposition (introduced in Iteration 4) could produce requirements that semantically duplicated already-elicited ones. In Iteration 5, each decomposed requirement text is compared against all existing requirement texts using `_message_similarity()` before being committed. Requirements with similarity > 0.6 to any existing requirement are discarded. Decomposition is also capped at **three domains per turn** (`FIX-CAP`) to bound latency.

### FIX-SEED — Implicit Subsystem Detection (`domain_discovery.py`)

The domain seeding prompt (`_SEED_PROMPT`) now includes an explicit instruction to infer a control-function domain for every physical device or sensor mentioned in the initial description, even if the stakeholder only named the device and not its function:

```
thermostat       → "Temperature Control"
dehumidifier     → "Humidity Control"
door locks       → "Door Lock Control"
alarm panel      → "Security Alarm Management"
cameras          → "Security Camera Monitoring"
```

This prevents the Iteration-4 failure where a stakeholder who said "I have a thermostat" produced no Temperature Control domain because they never used the phrase "temperature control" in their description.

### New Module — `srs_coverage.py` — IEEE-830 Section Completion

`SRSCoverageEnricher` is triggered inside `ConversationManager.finalize_session()` after the elicited requirements have been written to the SRS template but before the document is rendered. It fills IEEE-830 sections that elicitation dialogue cannot naturally produce, using hallucination-risk-tiered LLM prompts:

| Risk Tier                         | Sections                                                                                                                 | Strategy                                                                                                                                            |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| **LOW** (synthesis only)          | §1.2 Scope, §2.1 Product Perspective, §2.2 Product Functions, §2.3 User Classes, §2.5 Assumptions                        | LLM is given only the actual requirements and conversation excerpts; prompt explicitly bans introducing facts not present in the source             |
| **MEDIUM** (reasonable inference) | §2.4 Operating Environment, §2.6 User Documentation, §3.2.1 User Interfaces, §3.2.3 SW Interfaces, §3.2.4 Communications | LLM is given requirements plus the domain type; every inferred sentence is marked `[inferred]`                                                      |
| **HIGH** (no elicited data)       | §3.2.2 Hardware Interfaces, §3.4 Logical Database Requirements, §3.5 Design Constraints                                  | LLM is NOT asked to generate content freely; a formal stub is output with a checklist of items the architect must confirm before development begins |

Filled sections and their risk tiers are logged to the session log under the `srs_coverage_fill` event.

### Phase 4 — IEEE-830 Structural Completion Questions (`prompt_architect.py`)

A new Phase 4 is added to `TASK_BLOCK` between "all gates satisfied" and the SRS offer. After the domain gate and all NFRs are covered, the assistant asks about each remaining IEEE-830 structural section before offering SRS generation:

- §1.2 Scope — what is in/out of scope
- §2.1 Product Perspective — external system dependencies
- §2.3 User Classes — different user types and permissions
- §2.4 Operating Environment — hardware/OS/network constraints
- §2.6 User Documentation — help and instructions
- §2.7 Assumptions & Dependencies — external factors
- §3.1 External Interface Requirements — devices, APIs, protocols
- §3.2 System Features — any remaining feature areas
- §3.4 Design Constraints — regulatory or hardware limits

---

## Architecture

```
app.py                              ← Flask REST API + HTML/JS UI
src/components/
├── conversation_manager.py         ← Session orchestration, LLM providers, turn loop
│                                     FIX-LOOP, FIX-MATCH, FIX-DEDUP, FIX-CAP
├── conversation_state.py           ← Session state, requirement store, coverage tracking
│                                     FIX-NFR (is_ready_for_srs always checks NFRs)
├── domain_discovery.py             ← Dynamic domain gate: seed, reseed, probe, match, decompose
│                                     FIX-SEED, FIX-MATCH, FIX-2 (plain probes), FIX-3 (dedup context)
├── prompt_architect.py             ← 4-block dynamic prompt + phase structure
│                                     FIX-JARGON, FIX-NFR, FIX-DEPTH, Phase 4
├── srs_coverage.py                 ← NEW: IEEE-830 section completion with hallucination risk tiers
├── gap_detector.py                 ← IEEE-830/Volere checklist + domain gate gap injection
├── question_generator.py           ← Domain-first proactive question generation
├── requirement_extractor.py        ← Multi-strategy requirement extraction from responses
├── srs_template.py                 ← IEEE-830 data model, progressively populated
└── srs_formatter.py                ← Renders SRSTemplate to Markdown / plain text / JSON
output/                             ← Generated SRS documents (.md)
logs/                               ← JSON session logs (per-session, per-turn gap reports)
```

### System Prompt Structure (Iteration 5)

`PromptArchitect.build_system_message()` assembles four ordered blocks each turn:

```
=== ROLE ===
  ROLE_BLOCK — identity, communication style, jargon ban (FIX-JARGON)

=== CURRENT SESSION CONTEXT ===
  _build_context_block() output:
  - Turn count, FR/NFR counts
  - ⛔ HARD STOP / ✅ directive (domain gate or NFR gap)
  - Domain gate table with status icons
  - NFR coverage checklist
  - IEEE-830 structural coverage percentage

=== GAP DETECTION DIRECTIVE ===         (injected only when gap detector fires)
  ProactiveQuestionGenerator output

=== TASK INSTRUCTIONS ===
  TASK_BLOCK — Phase 1→2→3→4 structure, 8 non-negotiable rules
```

The `⛔ HARD STOP` mechanism introduced in Iteration 4 is extended in Iteration 5 to cover the NFR phase: a HARD STOP fires for each missing NFR category in turn, and the assistant is instructed to ask for specific measurable values. Only once all stops are cleared does the context block show `✅ ALL GATES SATISFIED`.

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
| `--port`     | `5000`      | TCP port                                |
| `--debug`    | off         | Flask debug mode                        |

---

## REST API

| Method | Endpoint                    | Description                                                    |
| ------ | --------------------------- | -------------------------------------------------------------- |
| `POST` | `/api/session/start`        | Start a new elicitation session                                |
| `POST` | `/api/session/turn`         | Send a user message, receive assistant reply + coverage report |
| `GET`  | `/api/session/status`       | Current coverage + gap report (no turn sent)                   |
| `POST` | `/api/session/generate_srs` | Trigger SRS generation (explicit; not automatic)               |
| `GET`  | `/api/session/download_srs` | Download the generated SRS `.md` file                          |
| `GET`  | `/api/health`               | Health check; returns provider name                            |

### `/api/session/turn` Response

```json
{
  "session_id": "...",
  "assistant_reply": "...",
  "turn_id": 7,
  "gap_report": { ... },
  "follow_up_questions": [ ... ],
  "coverage_pct": 58.3,
  "coverage_report": {
    "functional_count": 14,
    "nonfunctional_count": 6,
    "coverage_percentage": 58.3,
    "mandatory_nfrs_covered": false,
    "missing_mandatory_nfrs": ["Reliability & Availability Requirements"],
    "domain_gate_status": { "temperature_control": "confirmed", ... },
    "domain_gate_labels": { "temperature_control": "Temperature Control", ... },
    "domain_completeness_pct": 72
  },
  "srs_ready": false
}
```

`srs_ready` is `true` only when all three gates are satisfied (domain gate, all 6 mandatory NFRs, FR count ≥ 10) or the turn limit (60) is reached. It exposes the "Generate SRS" button in the UI but does not trigger generation automatically.

---

## Session Flow & Gates

### SRS Generation Readiness (three-way gate)

```
is_ready_for_srs() → True only when ALL of:
  1. functional_count ≥ 10
  2. mandatory_nfrs_covered (all 6 NFR categories have ≥ 1 requirement)
  3. domain_gate.is_satisfied (every domain CONFIRMED or EXCLUDED)
```

### Phase Structure

| Phase       | Turns             | Behaviour                                                                                         |
| ----------- | ----------------- | ------------------------------------------------------------------------------------------------- |
| **Phase 1** | 1–2               | Listen and build context; no requirements extracted yet                                           |
| **Phase 2** | 3+                | Work through domain gate: open question → extract `<REQ>` tags → one follow-up → next domain      |
| **Phase 3** | After domain gate | Mandatory NFR sweep: one question per missing NFR category, asking for specific measurable values |
| **Phase 4** | After all NFRs    | IEEE-830 structural questions (scope, user classes, operating environment, etc.) then SRS offer   |

### Domain Gate

`DomainGate` is seeded by `DomainDiscovery.seed()` on turn 1 using an LLM call that returns 8–12 functional domain labels derived from the stakeholder's initial description. It is re-seeded at turn 4 (first reseed) and turn 8 (second reseed, `SECOND_RESEED_TURN`) to catch domains that only become apparent after deeper conversation.

Each domain's `DomainSpec` holds:

- `status` — `unprobed` / `partial` / `confirmed` / `excluded`
- `req_ids` — IDs of requirements matched to this domain
- `sub_dimensions` — coverage across `data`, `actions`, `constraints`, `automation`, `edge_cases`
- `probe_count` — number of turns the domain has been actively probed
- `probe_question` — the current plain-language probe (regenerated when `probe_count > 0`)
- `decomposed` — whether LLM decomposition has been run for this domain

A domain reaches `confirmed` when it has ≥ 3 requirements covering ≥ 3 sub-dimensions, or when the LLM confirms it in a status update call.

---

## IEEE-830 Coverage Categories

The system tracks 12 IEEE-830 structural categories and 6 mandatory NFR categories:

**Structural (IEEE-830):**

| Key                | Label                                    |
| ------------------ | ---------------------------------------- |
| `purpose`          | System Purpose & Goals                   |
| `scope`            | System Scope & Boundaries                |
| `stakeholders`     | Stakeholders & User Classes              |
| `functional`       | Functional Requirements                  |
| `performance`      | Performance Requirements                 |
| `usability`        | Usability Requirements                   |
| `security_privacy` | Security & Privacy Requirements          |
| `reliability`      | Reliability & Availability Requirements  |
| `compatibility`    | Compatibility & Portability Requirements |
| `maintainability`  | Maintainability Requirements             |
| `constraints`      | Design & Implementation Constraints      |
| `interfaces`       | External Interfaces                      |

**Mandatory NFRs (all 6 required before SRS generation):**

| Key                | Label                                    |
| ------------------ | ---------------------------------------- |
| `performance`      | Performance Requirements                 |
| `usability`        | Usability & Accessibility Requirements   |
| `security_privacy` | Security & Privacy Requirements          |
| `reliability`      | Reliability & Availability Requirements  |
| `compatibility`    | Compatibility & Portability Requirements |
| `maintainability`  | Maintainability Requirements             |

---

## Ablation Study Support

The ablation study flag from previous iterations is retained:

```bash
# Gap detection ON (default)
python app.py --provider ollama

# Gap detection OFF — pass in /api/session/start body
curl -X POST http://localhost:5000/api/session/start \
     -H "Content-Type: application/json" \
     -d '{"gap_detection": false}'
```

When `gap_detection=false`, `GapDetector` returns a fully-covered dummy report, no proactive questions are generated, and no directive is injected into the prompt. All other behaviour — domain gate, NFR phase, SRS coverage enrichment — is unaffected, isolating the gap detection component.

---

## Output Files

### SRS Document (`output/srs_<session_id>.md`)

A full IEEE 830-1998 compliant specification including:

- §1 Introduction (purpose, scope, definitions, overview)
- §2 Overall Description (product perspective, functions, user characteristics, constraints, assumptions) — now filled by `srs_coverage.py` with risk-tiered LLM prompts
- §3 Specific Requirements (functional, interface, performance, reliability, security, maintainability, compatibility, usability)
- Appendix A: Traceability Matrix (req_id → section → source turn → SMART score)
- Appendix B: Coverage & Quality Report (domain completeness score, NFR coverage, SRS fill risk tiers)
- Appendix C: Conversation Transcript Summary

HIGH-risk sections (Hardware Interfaces, Logical Database Requirements, Design Constraints) contain formal stubs with architect checklists rather than LLM-generated content. MEDIUM-risk inferred sentences are marked `[inferred]` for reviewer validation.

### Session Log (`logs/session_<session_id>.json`)

Structured JSON log with per-turn gap reports, domain gate status, and a new `srs_coverage_fill` event at finalisation recording which sections were filled and at what risk tier.

---

## LLM Providers

| Provider | Class            | Env Var          | Notes                                           |
| -------- | ---------------- | ---------------- | ----------------------------------------------- |
| `openai` | `OpenAIProvider` | `OPENAI_API_KEY` | GPT-4o by default                               |
| `ollama` | `OllamaProvider` | `OLLAMA_API_KEY` | Hildesheim server; `OLLAMA_BASE_URL` optional   |
| `stub`   | `StubProvider`   | —                | Deterministic scripted responses for UI testing |

Temperature is fixed at `0.0` for the main conversation loop and all classification LLM calls for reproducible evaluation runs. Domain probe generation uses `temperature=0.3` to produce varied wording. The decomposition call uses `temperature=0.2`.

---

## Troubleshooting

**Conversation keeps asking the same question**
This was the primary Iteration-4 loop bug, fixed by `FIX-LOOP`. If it recurs, check that `conversation_manager.py` is from Iteration 5. Confirm via `GET /api/health` that the server restarted after the code update.

**Probe questions contain technical jargon**
`FIX-JARGON` and `FIX-2` address this. If jargon appears, the probe question may have been generated by the Iteration-4 fallback path. Ensure `domain_discovery.py` is Iteration 5 and that the LLM provider is reachable (probe generation falls back to a template string on API failure).

**`srs_ready` stays `false` after many turns**
Check the coverage panel for: (1) any domain still `unprobed` or `partial`, (2) any NFR category with 0 requirements. The context block will show a `⛔ HARD STOP` directive identifying the specific blocker. With `MIN_FUNCTIONAL_REQS = 10` the minimum viable session now requires more turns than in previous iterations.

**SRS §2.x sections are empty**
`srs_coverage.py` only runs at finalisation (`POST /api/session/generate_srs`). If the file is missing or the `create_enricher` import fails, check that `srs_coverage.py` is present in `src/components/` and the provider is reachable.

**SRS contains only `NOT ELICITED` placeholders**
The conversation was too short or lacked clear requirement statements. The coverage panel shows both the domain gate status and IEEE-830 scores — address any `UNPROBED` domains and uncovered NFR categories before generating.

**Ollama connection error**
Verify that `OLLAMA_API_KEY` is set and the university VPN is active if required.

**OpenAI authentication error**
Verify that `OPENAI_API_KEY` is set and has sufficient quota.

**Port already in use**

```bash
python app.py --port 5001
```

---

## Research Foundation

Iteration 5 directly addresses five failure modes identified in the Iteration-4 post-mortem:

- **`FIX-LOOP`** eliminates the conversation loop failure mode by detecting duplicate user messages with Jaccard similarity and force-advancing stuck domains.
- **`FIX-JARGON`** improves stakeholder comprehension by generating probe questions with a dedicated LLM call that enforces plain language and concrete examples.
- **`FIX-NFR`** closes the NFR gating loophole by making `mandatory_nfrs_covered` an unconditional prerequisite in `is_ready_for_srs()`.
- **`FIX-MATCH`** improves requirement traceability by replacing substring matching with LLM-based domain assignment.
- **`srs_coverage.py`** addresses the persistent gap between high elicitation coverage scores and low SRS completeness scores by filling structural IEEE-830 sections at finalisation with hallucination-risk-tiered prompts.
- **Phase 4** ensures that IEEE-830 structural sections are explicitly elicited before the SRS is offered, providing grounded input for the coverage enricher.

---

## License

Academic Research Project — University of Hildesheim

Team members: Hunain Murtaza (1750471) · David Tashjian (1750243) · Saad Younas (1750124) · Amine Rafai (1749821) · Khaled Shaban (1750283) · Mohammad Alsaiad (1750755)
