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
2. **Ollama** installed and running
3. **Llama 3.1:8b model** pulled in Ollama

### Installing Ollama & Model

```bash
# Install Ollama (Linux/Mac)
curl -fsSL https://ollama.com/install.sh | sh

# Windows: Download from https://ollama.com/download

# Pull Llama 3.1:8b model
ollama pull llama3.1:8b

# Verify Ollama is running
ollama list
```

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

### 1. Start Ollama (if not already running)

```bash
# Ollama typically runs as a background service
# If not, start it manually:
ollama serve
```

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

### Ollama Connection Error
```
Error: I'm having trouble connecting to the language model
```
**Solution:** Ensure Ollama is running (`ollama serve`) and Llama 3.1 is pulled

### Port Already in Use
```
Error: Address already in use
```
**Solution:** Change port in `app.py` line 146:
```python
app.run(host='0.0.0.0', port=5001, debug=True)  # Changed from 5000
```

### Empty Responses
```
Assistant returns empty or generic responses
```
**Solution:** Check Ollama model is loaded correctly:
```bash
ollama list
ollama ps  # Shows running models
```

## Research Foundation

This implementation is based on systematic literature review findings:

- **Conversational Elicitation**: Papers [2][4][28]
- **4W Analysis**: Paper [31]
- **Ambiguity Detection**: Paper [29]
- **Chain-of-Thought Prompting**: Paper [26]
- **IEEE-830 Standard**: Paper [31]

## Future Work (Next Phases)

**Iteration 1 - Phase 2:**
- Enhanced completeness checking with automated gap detection
- UML diagram generation (sequence/deployment diagrams)
- Multi-stakeholder support
- Traceability links

**Iteration 2:**
- Advanced verification (consistency checking, conflict detection)
- Integration with requirements management tools
- RAG with domain-specific knowledge bases

**Iteration 3:**
- Multi-agent collaboration
- Real-time validation during elicitation
- Extended IEEE-830 compliance checking

## License

Academic Research Project - Team Members:
- Hunain Murtaza (1750471)
- David Tashjian (1750243)
- Saad Younas (1750124)
- Amine Rafai (1749821)
- Khaled Shaban (1750283)
- Mohammad Alsaiad (1750755)

---

**Note:** This is an MVP (Minimum Viable Product) for initial testing and evaluation. Future iterations will add more sophisticated features based on the DSR methodology.
