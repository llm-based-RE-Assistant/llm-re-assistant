"""
LLM-Based Requirements Engineering Assistant - Iteration 1 MVP
Flask Application Entry Point
"""

from flask import Flask, render_template, request, jsonify, session
from datetime import datetime
import json
import os
from dotenv import load_dotenv
from src.utils.ollama_client import OllamaClient
from src.utils.openai_client import OpenAIClient
from src.utils.conversation_manager import ConversationManager
from src.elicitation.elicitation_engine import ElicitationEngine
from src.agents.modeling_agent import ModelingAgent

# Load environment variables from .env file
# Try multiple locations: same dir as app.py, then current directory
app_dir = os.path.dirname(os.path.abspath(__file__))
env_paths = [
    os.path.join(app_dir, '.env'),  # Same directory as app.py
    '.env',  # Current working directory
    os.path.join(os.getcwd(), '.env')  # Explicit current directory
]

loaded = False
for env_path in env_paths:
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path, override=True)
        if os.getenv('OPENAI_API_KEY'):
            print(f"✓ Loaded .env from: {env_path}")
            loaded = True
            break

if not loaded:
    # Last attempt: just call load_dotenv() which searches automatically
    load_dotenv(override=True)
    if os.getenv('OPENAI_API_KEY'):
        print("✓ Loaded .env (auto-detected)")
    else:
        print("⚠ .env file not found or OPENAI_API_KEY not set")

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Initialize components
# Try to use Ollama first, fallback to OpenAI if not available
llm_client = None
use_ollama = os.getenv('USE_OLLAMA', 'true').lower() == 'true'

if use_ollama:
    try:
        ollama_base_url = os.getenv('LLM_SERVER_URL', 'https://genai-01.uni-hildesheim.de')
        # Ensure base_url includes /ollama if not already present
        if not ollama_base_url.endswith('/ollama'):
            ollama_base_url = ollama_base_url.rstrip('/') + '/ollama'
        ollama_model = os.getenv('OLLAMA_MODEL', 'qwen2.5:32b')
        ollama_client = OllamaClient(base_url=ollama_base_url, model=ollama_model)
        # Test connection
        if ollama_client.check_connection():
            llm_client = ollama_client
            print("✓ Using Ollama for elicitation engine")
        else:
            print("⚠ Ollama not available, falling back to OpenAI")
            llm_client = None
    except Exception as e:
        print(f"⚠ Ollama initialization failed: {e}, falling back to OpenAI")
        llm_client = None

# Fallback to OpenAI if Ollama is not available
if llm_client is None:
    try:
        llm_client = OpenAIClient(
            model=os.getenv('OPENAI_MODEL', 'gpt-4'),
            temperature=0.7
        )
        print("✓ Using OpenAI for elicitation engine")
    except Exception as e:
        print(f"⚠ OpenAI initialization failed: {e}")
        print("⚠ Both Ollama and OpenAI failed to initialize. Some features may not work.")
        # Create a dummy client that will show error messages
        llm_client = None

conversation_manager = ConversationManager()
if llm_client:
    elicitation_engine = ElicitationEngine(llm_client)
else:
    # Create a dummy engine that shows error messages
    elicitation_engine = None

modeling_agent = ModelingAgent()

# Ensure artifacts directory exists
os.makedirs('artifacts', exist_ok=True)
os.makedirs('artifacts/conversations', exist_ok=True)
os.makedirs('artifacts/specifications', exist_ok=True)


@app.route('/')
def index():
    """Render the main chatbot interface"""
    return render_template('index.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Handle chat messages from user
    Expected JSON: {"message": "user message text"}
    Returns: {"response": "assistant response", "status": "success"}
    """
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({
                'status': 'error',
                'response': 'Please provide a message.'
            }), 400
        
        # Get or create session ID
        session_id = session.get('session_id')
        if not session_id:
            session_id = conversation_manager.create_session()
            session['session_id'] = session_id
        
        # Add user message to conversation history
        conversation_manager.add_message(session_id, 'user', user_message)
        
        # Get conversation context
        conversation_history = conversation_manager.get_conversation(session_id)
        
        # Process message through elicitation engine
        if elicitation_engine is None:
            return jsonify({
                'status': 'error',
                'response': 'LLM service is not available. Please check your Ollama or OpenAI configuration.'
            }), 500
        
        assistant_response = elicitation_engine.process_message(
            user_message, 
            conversation_history
        )
        
        # Add assistant response to conversation history
        conversation_manager.add_message(session_id, 'assistant', assistant_response)
        
        # Save conversation periodically
        conversation_manager.save_conversation(session_id)
        
        return jsonify({
            'status': 'success',
            'response': assistant_response
        })
        
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        return jsonify({
            'status': 'error',
            'response': 'An error occurred processing your message. Please try again.'
        }), 500


@app.route('/api/generate-spec', methods=['POST'])
def generate_specification():
    """
    Generate IEEE-830 specification draft from conversation history
    """
    try:
        session_id = session.get('session_id')
        
        if not session_id:
            return jsonify({
                'status': 'error',
                'message': 'No active conversation session found.'
            }), 400
        
        # Get conversation history
        conversation_history = conversation_manager.get_conversation(session_id)
        
        if len(conversation_history) < 2:
            return jsonify({
                'status': 'error',
                'message': 'Not enough conversation data to generate specification.'
            }), 400
        
        # Generate specification using elicitation engine
        if elicitation_engine is None:
            return jsonify({
                'status': 'error',
                'message': 'LLM service is not available. Please check your Ollama or OpenAI configuration.'
            }), 500
        
        specification = elicitation_engine.generate_specification(conversation_history)
        
        # Save specification to artifacts
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        spec_filename = f'artifacts/specifications/srs_{session_id}_{timestamp}.txt'
        
        with open(spec_filename, 'w', encoding='utf-8') as f:
            f.write(specification)
        
        return jsonify({
            'status': 'success',
            'specification': specification,
            'filename': spec_filename
        })
        
    except Exception as e:
        print(f"Error generating specification: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'An error occurred generating the specification.'
        }), 500


@app.route('/api/new-session', methods=['POST'])
def new_session():
    """Start a new conversation session"""
    try:
        # Clear current session
        session.pop('session_id', None)
        
        # Create new session
        session_id = conversation_manager.create_session()
        session['session_id'] = session_id
        
        return jsonify({
            'status': 'success',
            'session_id': session_id,
            'message': 'New session started successfully.'
        })
        
    except Exception as e:
        print(f"Error creating new session: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'An error occurred creating a new session.'
        }), 500


@app.route('/api/generate-uml', methods=['POST'])
def generate_uml():
    """
    Generate UML class diagram from requirements
    Input: Session ID or explicit requirements text
    Output: PlantUML code + quality assessment
    """
    try:
        data = request.get_json() or {}
        session_id = session.get('session_id')
        explicit_requirements = data.get('requirements', '').strip()
        
        # Get requirements from session or explicit input
        if explicit_requirements:
            requirements = explicit_requirements
            conversation_history = None
        elif session_id:
            conversation_history = conversation_manager.get_conversation(session_id)
            if not conversation_history or len(conversation_history) < 2:
                return jsonify({
                    'status': 'error',
                    'message': 'Not enough conversation data to generate UML. Provide requirements or continue the conversation.'
                }), 400
            requirements = ''  # Will be extracted from conversation by the agent
        else:
            return jsonify({
                'status': 'error',
                'message': 'No active session or requirements provided. Start a conversation or provide requirements text.'
            }), 400
        
        # Generate UML diagram
        result = modeling_agent.generate_uml(
            requirements=requirements,
            conversation_history=conversation_history if session_id else None
        )
        
        if result['status'] == 'error':
            return jsonify(result), 400
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error generating UML: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'An error occurred generating the UML diagram: {str(e)}',
            'plantuml_code': '',
            'quality': {
                'completeness_ratio': 0.0,
                'entities_found': 0,
                'entities_expected': 0,
                'warnings': [f"Generation failed: {str(e)}"]
            }
        }), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)