# LLM-Based Requirements Engineering Assistant - Iteration 1 MVP

## Project Overview

This is the initial phase of Iteration 1 for an LLM-based Requirements Engineering Assistant. The system provides conversational requirements elicitation using Ollama's Llama 3.1 model and generates IEEE-830 compliant SRS drafts.

### Implemented Features (Iteration 1 - Initial Phase)

✅ **Conversational Elicitation**
- Multi-turn dialogue with context memory
- Chain-of-Thought prompting for adaptive questioning
- Natural language interaction

✅ **Interactive Clarification** 
- Ambiguity detection (vague words, weak phrases)
- 4W analysis framework (Who/What/When/Where)
- Follow-up question generation

✅ **Basic Specification Generation**
- IEEE-830 template structure
- Automated SRS draft generation
- Sections: Introduction, Overall Description, Functional/Non-Functional Requirements

✅ **Session Management**
- Persistent conversation storage
- Artifact generation and storage
- Multi-session support

## Directory Structure

```
llm-re-assistant/
├── artifacts/
│   ├── conversations/      # Stored conversation history (JSON)
│   └── specifications/     # Generated SRS documents
├── docs/                   # Documentation
├── src/
│   ├── elicitation/
│   │   └── elicitation_engine.py   # Core elicitation logic
│   ├── modeling/                    # (Future: Iteration 1 Phase 2)
│   ├── specification/               # (Future: Iteration 1 Phase 2)
│   ├── verification/                # (Future: Iteration 1 Phase 2)
│   └── utils/
│       ├── ollama_client.py         # Ollama API integration
│       └── conversation_manager.py  # Session & history management
├── templates/
│   └── index.html          # Web interface
├── tests/                  # Unit tests (Future)
├── venv/                   # Python virtual environment
├── app.py                  # Flask application entry point
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## Prerequisites

1. **Python 3.8+** installed
2. **Ollama** server api key
3. **Llama 3.1:8b model** check on ollama server or choose any other.


## Installation

### 1. Clone/Setup Project

```bash
cd llm-re-assistant
```

### 2. Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On Linux/Mac:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Verify Directory Structure

Ensure the following directories exist:
```bash
mkdir -p artifacts/conversations
mkdir -p artifacts/specifications
mkdir -p templates
mkdir -p src/elicitation
mkdir -p src/utils
```

## Running the Application

### 1. Get Ollama Server API

```bash
# Generate ollama server api from University LLM Server
Visit this link https://genai-01.uni-hildesheim.de/
```
If you don't have access to University Server then you can also locally setup ollama server.
To download ollama server, visit this link `https://ollama.com/download`

### 2. Run Flask Application

```bash
# Make sure virtual environment is activated
python app.py
```

The application will start on `http://localhost:5000`

### 3. Access Web Interface

Open your browser and navigate to:
```
http://localhost:5000
```

## Using the Application

### Starting a Conversation

1. The interface will greet you with a welcome message
2. Type your project idea or requirements (e.g., "I want to build a library management system")
3. The assistant will ask adaptive follow-up questions to elicit requirements
4. Answer questions naturally - the system uses 4W analysis to ensure completeness

### Generating SRS Document

1. After discussing requirements, click **"Generate SRS"** button
2. The system will create an IEEE-830 compliant specification
3. The specification appears in the chat and is saved to `artifacts/specifications/`

### Starting New Session

1. Click **"New Session"** button
2. Current conversation is saved automatically
3. A fresh session begins for a new project

## API Endpoints

### POST `/api/chat`
Send a message to the assistant
```json
Request: {"message": "I want to build a CRM system"}
Response: {"status": "success", "response": "Great! Let me help you..."}
```

### POST `/api/generate-spec`
Generate SRS specification from conversation
```json
Response: {
  "status": "success", 
  "specification": "# SOFTWARE REQUIREMENTS SPECIFICATION...",
  "filename": "artifacts/specifications/srs_xxx.txt"
}
```

### POST `/api/new-session`
Start a new conversation session
```json
Response: {"status": "success", "session_id": "uuid", "message": "..."}
```

### GET `/api/health`
Health check endpoint
```json
Response: {"status": "healthy", "timestamp": "2025-01-15T10:30:00"}
```

## Configuration

### Changing LLM Model

Edit `app.py` line 16:
```python
ollama_client = OllamaClient(model="llama3.1:8b")  # Change model here
```

Available models (after pulling with `ollama pull`):
- `llama3.1:8b` (default)
- `llama3.1:70b` (better quality, slower)
- `mistral:7b`
- `codellama:13b`

### Adjusting Temperature

Edit `src/elicitation/elicitation_engine.py`:
- Line 114: `temperature=0.7` (conversational responses)
- Line 137: `temperature=0.3` (specification generation - more consistent)

## Troubleshooting

**NFR gate does not clear after giving one answer per category**
This is expected behaviour in Iteration 6. `MIN_NFR_PER_CATEGORY` is now 2. The `🔶` icon in the coverage panel indicates a category has some coverage but is below threshold. The depth probe will ask for a specific measurable follow-up.

**Phase 4 questions appear after I said "I think that covers it"**
This is correct. The `ROLE_BLOCK` instructs the assistant not to agree with session-closing phrases while a `⛔ HARD STOP` is active. Phase 4 must complete all 8 sections before the SRS offer is made.

**`srs_ready` stays `false` after all NFRs appear green**
Check the Phase 4 section progress panel. `is_ready_for_srs()` now also requires `len(phase4_sections_covered) >= len(PHASE4_SECTIONS)`. The panel shows which sections are still `⬜`.

**`<SECTION>` tags missing from assistant responses**
The LLM did not emit the tag after the Phase 4 answer. This can happen if the answer was very short and the follow-up path was taken. Verify that `prompt_architect.py` is Iteration 6 (check for the `<SECTION id="...">` format rule in `TASK_BLOCK`) and that the provider is reachable.

**Conversation keeps asking the same question**
See Iteration 5 `FIX-LOOP`. If it recurs, confirm `conversation_manager.py` is Iteration 5+ and restart the server.

**Probe questions contain technical jargon**
See Iteration 5 `FIX-JARGON`. Ensure `domain_discovery.py` is current and the provider is reachable (probe generation falls back to a template string on API failure).

**SRS §2.x sections are empty despite Phase 4 completing**
`srs_coverage.py` acts as a fallback for sections not covered by Phase 4 tags. If both Phase 4 content and `srs_coverage.py` are missing, verify the provider is reachable at finalisation and that `srs_coverage.py` exists in `src/components/`.

**Ollama connection error**
Verify `OLLAMA_API_KEY` is set and the university VPN is active if required.

**OpenAI authentication error**
Verify `OPENAI_API_KEY` is set and has sufficient quota.

**Port already in use**

```bash
python app.py --port 5001
```

---

## Research Foundation

Iteration 6 addresses three failure modes identified in the Iteration-5 post-mortem:

- **`IT6-NFR-DEPTH`** closes a gating loophole where one vague requirement was sufficient to satisfy a mandatory NFR category. Raising `MIN_NFR_PER_CATEGORY` to 2 and adding a depth probe forces the assistant to elicit at least one measurable follow-up per category.
- **`IT6-PHASE4`** addresses the persistent gap between high domain/NFR coverage scores and low SRS structural completeness. By making Phase 4 a hard gate before the SRS offer, all eight narrative IEEE-830 sections are explicitly elicited from the stakeholder rather than inferred or left empty.
- **`IT6-VOLERE`** removes conceptual ambiguity introduced by mixing two incompatible standards. All artefacts now use IEEE 830-1998 exclusively, ensuring consistent section numbering and terminology across prompts, state, and output documents.

---

## License

Academic Research Project - Team Members:
- Hunain Murtaza
- David Tashjian
- Saad Younas
- Khaled Shaban
- Mohammad Alsaiad

---

**Note:** This is an MVP (Minimum Viable Product) for initial testing and evaluation. Future iterations will add more sophisticated features based on the DSR methodology.
