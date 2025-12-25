"""
LLM-Based Requirements Engineering Assistant - Iteration 2
Flask Application with Multi-Agent Architecture

Integrates GPT-4 Elicitation Agent with existing Iteration 1 infrastructure
"""

from flask import Flask, render_template, request, jsonify, session
from datetime import datetime
from dotenv import load_dotenv
import json
import os
from pathlib import Path

# Iteration 1 components (existing)
from src.utils.ollama_client import OllamaClient
from src.utils.conversation_manager import ConversationManager
from src.elicitation.elicitation_engine import ElicitationEngine

# Iteration 2 component (new)
from src.agents.elicitation_agent import ElicitationAgent

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Configuration: Choose which agent to use
USE_GPT4_AGENT = os.getenv("USE_GPT4_AGENT", "false").lower() == "true"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize Iteration 1 components (Ollama-based)
ollama_client = OllamaClient(model="llama3.1:8b")
conversation_manager = ConversationManager()
elicitation_engine_v1 = ElicitationEngine(ollama_client)

# Initialize Iteration 2 component (GPT-4 agent) if enabled
elicitation_agent_v2 = None
if USE_GPT4_AGENT and OPENAI_API_KEY:
    try:
        elicitation_agent_v2 = ElicitationAgent(
            api_key=OPENAI_API_KEY,
            model=os.getenv("OPENAI_MODEL", "gpt-4"),
            temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
            fallback_model=os.getenv("OPENAI_FALLBACK_MODEL", "gpt-3.5-turbo")
        )
        print(f" Iteration 2: GPT-4 Elicitation Agent initialized ({elicitation_agent_v2.model})")
    except Exception as e:
        print(f"âš ï¸  Warning: Could not initialize GPT-4 agent: {e}")
        print("    Falling back to Iteration 1 (Ollama) agent")
        USE_GPT4_AGENT = False
else:
    print("â„¹ï¸  Using Iteration 1 (Ollama) agent - Set USE_GPT4_AGENT=true to enable GPT-4")

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
    
    Iteration 2 Enhancement:
    - Routes to GPT-4 ElicitationAgent if enabled
    - Falls back to Iteration 1 ElicitationEngine (Ollama) if not
    - Creates artifacts with metadata when using GPT-4
    - Maintains backward compatibility
    """
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({
                'status': 'error',
                'response': 'Please provide a message.'
            }), 400
        
        # Get or create session ID (using existing ConversationManager)
        session_id = session.get('session_id')
        if not session_id:
            session_id = conversation_manager.create_session()
            session['session_id'] = session_id
        
        # Add user message to conversation history
        conversation_manager.add_message(session_id, 'user', user_message)
        
        # Get conversation context
        conversation_history = conversation_manager.get_conversation(session_id)
        
        # Get project description from metadata if available
        session_data = conversation_manager.sessions.get(session_id, {})
        project_description = session_data.get('metadata', {}).get('project_description', '')
        
        # ROUTING LOGIC: Use GPT-4 agent if enabled, otherwise use Iteration 1 engine
        if USE_GPT4_AGENT and elicitation_agent_v2:
            # === ITERATION 2: GPT-4 Agent ===
            try:
                # Convert to format expected by GPT-4 agent (role + content only, no timestamps)
                history_for_agent = [
                    {'role': msg['role'], 'content': msg['content']}
                    for msg in conversation_history[:-1]  # Exclude current user message
                ]
                
                # Call GPT-4 agent with Chain-of-Thought prompting
                assistant_response, artifact, metadata = elicitation_agent_v2.elicit_requirements(
                    user_message=user_message,
                    conversation_history=history_for_agent,
                    project_description=project_description,
                    session_id=session_id
                )
                
                # Store artifact in ConversationManager if created
                if artifact:
                    requirement = {
                        'id': artifact.artifact_id,
                        'content': artifact.content,
                        'confidence': artifact.confidence_score,
                        'source_turn': artifact.metadata.get('source_turn'),
                        'created_at': artifact.created_at,
                        'agent': 'GPT4_ElicitationAgent_v2'
                    }
                    conversation_manager.add_requirement(session_id, requirement)
                
                # Update project description if first turn and not set
                if not project_description and len(conversation_history) <= 2:
                    # Try to extract project context from first exchange
                    if 'system' in user_message.lower() or 'application' in user_message.lower():
                        conversation_manager.update_metadata(session_id, 'project_description', user_message)
                
                # Add assistant response to conversation history
                conversation_manager.add_message(session_id, 'assistant', assistant_response)
                
                # Save conversation
                conversation_manager.save_conversation(session_id)
                
                # Return response with Iteration 2 metadata
                return jsonify({
                    'status': 'success',
                    'response': assistant_response,
                    'agent': 'ElicitationAgent_v2_GPT4',
                    'iteration': 2,
                    'artifact': {
                        'id': artifact.artifact_id,
                        'content': artifact.content,
                        'confidence': artifact.confidence_score,
                        'metadata': artifact.metadata
                    } if artifact else None,
                    'metadata': {
                        'turn': metadata.get('turn'),
                        'incompleteness_analysis': metadata.get('incompleteness_analysis'),
                        'token_usage': metadata.get('usage')
                    },
                    'usage_stats': elicitation_agent_v2.get_usage_stats()
                })
            
            except Exception as e:
                print(f" GPT-4 agent error: {e}")
                print("   Falling back to Iteration 1 (Ollama) agent...")
                # Fall through to Iteration 1 logic below
        
        # === ITERATION 1: Ollama-based Engine (Fallback or Default) ===
        assistant_response = elicitation_engine_v1.process_message(
            user_message, 
            conversation_history
        )
        
        # Add assistant response to conversation history
        conversation_manager.add_message(session_id, 'assistant', assistant_response)
        
        # Save conversation periodically
        conversation_manager.save_conversation(session_id)
        
        return jsonify({
            'status': 'success',
            'response': assistant_response,
            'agent': 'ElicitationEngine_v1_Ollama',
            'iteration': 1
        })
        
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        return jsonify({
            'status': 'error',
            'response': 'An error occurred processing your message. Please try again.'
        }), 500


@app.route('/api/generate-spec', methods=['POST'])
def generate_spec():
    """Generate SRS specification from conversation using the same model"""
    try:
        session_id = session.get('session_id')
        
        if not session_id:
            return jsonify({'status': 'error', 'message': 'No active session'}), 400
        
        filepath = Path(f'artifacts/conversations/{session_id}.json')
        if not filepath.exists():
            return jsonify({'status': 'error', 'message': f'Session not found'}), 404
        
        with open(filepath, 'r') as f:
            conversation = json.load(f)
        
        requirements = conversation.get('requirements', [])
        messages = conversation.get('messages', [])
        metadata = conversation.get('metadata', {})
        
        if not requirements and not messages:
            return jsonify({'status': 'error', 'message': 'No requirements found'}), 400
        
        # Build context
        context = "Generate an IEEE-830 compliant SRS based on:\n\n"
        context += "=== CONVERSATION ===\n"
        for msg in messages[-10:]:
            context += f"{msg.get('role', '').upper()}: {msg.get('content', '')}\n\n"
        
        if requirements:
            context += "\n=== REQUIREMENTS ===\n"
            for i, req in enumerate(requirements, 1):
                req_text = req.get('description', '') if isinstance(req, dict) else str(req)
                context += f"{i}. {req_text}\n"
        
        context += "\nGenerate a complete IEEE-830 SRS with Introduction, Overall Description, Functional Requirements, and Non-Functional Requirements."
        
        # SMART MODEL DETECTION        
        session_model = ''
        
        # Check agent field
        if 'elicited_requirements' in metadata:
            reqs = metadata.get('elicited_requirements', [])
            if reqs and len(reqs) > 0:
                session_model = reqs[0].get('agent', '').lower()
        
        file_size = filepath.stat().st_size
        is_large_session = file_size > 5000  
        
        print(f"\n{'='*60}")
        print(f"SRS GENERATION")
        print(f"{'='*60}")
        print(f"Session: {session_id}")
        print(f"Size: {file_size} bytes")
        print(f"Agent: {session_model or 'Unknown'}")
        print(f"Messages: {len(messages)}")
        print(f"Requirements: {len(requirements)}")
        
        # Decision logic
        if 'gpt' in session_model or 'gpt4' in session_model:
            use_openai = True
            reason = f"GPT-4 agent detected"
        elif 'llama' in session_model or 'qwen' in session_model:
            use_openai = False
            reason = f"Ollama agent detected"
        elif is_large_session:
            use_openai = True
            reason = f"Large session ({file_size}B)  GPT-4"
        else:
            use_openai = False
            reason = f"Small session ({file_size}B)  Ollama"
        
        print(f"Using: {'GPT-4' if use_openai else 'Ollama'}")
        print(f"Reason: {reason}")
        print(f"{'='*60}\n")
        
        # GENERATE        
        if use_openai:
            from openai import OpenAI
            
            openai_api_key = os.getenv('OPENAI_API_KEY')  
            if not openai_api_key:
                return jsonify({'status': 'error', 'message': 'OpenAI key missing'}), 500
            
            try:
                client = OpenAI(api_key=openai_api_key) 
                response = client.chat.completions.create(
                    model=os.getenv('OPENAI_MODEL', 'gpt-4'),
                    messages=[
                        {"role": "system", "content": "You are an expert requirements engineer."},
                        {"role": "user", "content": context}
                    ],
                    temperature=0.7,
                    max_tokens=4000
                )
                specification = response.choices[0].message.content
                print(f"✅ GPT-4: {len(specification)} chars")
            except Exception as e:
                print(f"❌ OpenAI error: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
        else:
            # Use University LLM Server (Qwen)
            import requests
            
            llm_server_url = os.getenv('LLM_SERVER_URL', 'http://localhost:11434')
            model = os.getenv('OLLAMA_MODEL', 'qwen2.5:32b')
            api_key = os.getenv('OLLAMA_API_KEY', '')
            
            print(f"Using LLM server: {llm_server_url}")
            print(f"Using model: {model}")
            
            try:
                headers = {}
                if api_key:
                    headers['Authorization'] = f'Bearer {api_key}'
                
                resp = requests.post(
                    f'{llm_server_url}/api/generate',
                    json={
                        'model': model,
                        'prompt': context,
                        'stream': False
                    },
                    headers=headers,
                    timeout=180,
                    verify=False  # University server may have self-signed cert
                )
                
                if resp.status_code == 200:
                    specification = resp.json().get('response', '')
                    print(f" {model}: {len(specification)} chars")
                else:
                    print(f" Server returned {resp.status_code}: {resp.text}")
                    return jsonify({
                        'status': 'error',
                        'message': f'LLM server error: {resp.status_code}'
                    }), 500
                    
            except requests.exceptions.ConnectionError as e:
                print(f" Connection error: {e}")
                return jsonify({
                    'status': 'error',
                    'message': f'Cannot connect to {llm_server_url}. Check VPN/network connection.'
                }), 500
            except Exception as e:
                print(f" Error: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        return jsonify({
            'status': 'success',
            'specification': specification,
            'metadata': {'model': 'GPT-4' if use_openai else 'Ollama', 'reason': reason}
        })
        
    except Exception as e:
        print(f" Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@app.route('/api/sessions', methods=['GET'])
def list_sessions():
    """List all saved conversation sessions with metadata"""
    try:
        conversations_dir = Path('artifacts/conversations')
        
        if not conversations_dir.exists():
            return jsonify({'status': 'success', 'sessions': []})
        
        sessions = []
        
        for filepath in conversations_dir.glob('*.json'):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                
                session_id = filepath.stem
                messages = data.get('messages', [])
                requirements = data.get('requirements', [])
                metadata = data.get('metadata', {})
                
                # Get title from first user message
                title = "Conversation"
                for msg in messages:
                    if msg.get('role') == 'user':
                        title = msg.get('content', '')[:50]
                        if len(msg.get('content', '')) > 50:
                            title += '...'
                        break
                
                created_at = data.get('created_at', datetime.now().isoformat())
                updated_at = data.get('updated_at', created_at)
                
                # Detect model from agent or file structure
                agent = ''
                if 'elicited_requirements' in metadata:
                    reqs = metadata.get('elicited_requirements', [])
                    if reqs and len(reqs) > 0:
                        agent = reqs[0].get('agent', '').lower()

                # Also check requirements array as fallback
                if not agent:
                    for req in requirements:
                        if isinstance(req, dict) and 'agent' in req:
                            agent = req.get('agent', '').lower()
                            break

                file_size = filepath.stat().st_size
                
                # KEY DETECTION: Iteration 1 (Ollama/Qwen) doesn't create requirements
                # Iteration 2 (GPT-4) always creates requirements with agent field
                has_requirements_with_agent = any(
                    isinstance(req, dict) and 'agent' in req
                    for req in requirements
                )

                # Determine iteration/model
                if 'gpt' in agent or 'gpt4' in agent or 'openai' in agent:
                    # Explicit GPT-4 agent marker found
                    iteration = 2
                    model = 'gpt-4'
                elif 'llama' in agent or 'qwen' in agent or 'ollama' in agent:
                    # Explicit Ollama agent marker found
                    iteration = 1
                    model = 'qwen2.5:32b'
                elif has_requirements_with_agent:
                    # Has requirements with agent field = GPT-4
                    iteration = 2
                    model = 'gpt-4'
                elif len(requirements) == 0 and len(messages) > 0:
                    # No requirements but has messages = Ollama/Qwen (Iteration 1)
                    iteration = 1
                    model = 'qwen2.5:32b'
                elif file_size < 3000:  
                    iteration = 1
                    model = 'ollama (likely)'
                else:
                    # Default to Iteration 1 for unclear cases
                    iteration = 1
                    model = 'qwen2.5:32b (likely)'

                
                sessions.append({
                    'session_id': session_id,
                    'title': title,
                    'message_count': len(messages),
                    'created_at': created_at,
                    'updated_at': updated_at,
                    'iteration': iteration,
                    'model': model
                })
            except Exception as e:
                print(f"Error reading {filepath}: {e}")
                continue
        
        sessions.sort(key=lambda x: x['updated_at'], reverse=True)
        
        return jsonify({'status': 'success', 'sessions': sessions, 'count': len(sessions)})
    except Exception as e:
        print(f"Error listing sessions: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/load-session', methods=['POST'])
def load_session():
    """Load a specific conversation session"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({
                'status': 'error',
                'message': 'session_id is required'
            }), 400
        
        filepath = Path(f'artifacts/conversations/{session_id}.json')
        
        if not filepath.exists():
            return jsonify({
                'status': 'error',
                'message': f'Session {session_id} not found'
            }), 404
        
        with open(filepath, 'r') as f:
            conversation = json.load(f)
        
        if not conversation:
            return jsonify({
                'status': 'error',
                'message': f'Session {session_id} not found'
            }), 404
        
        session['session_id'] = session_id  
        
        messages = conversation.get('messages', [])
        requirements = conversation.get('requirements', [])
        metadata = conversation.get('metadata', {})
        
        return jsonify({
            'status': 'success',
            'session_id': session_id, 
            'messages': messages,
            'requirements': requirements,
            'metadata': metadata,
            'message_count': len(messages),
        })
    except Exception as e:
        print(f"Error loading session: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to load session: {str(e)}'
        }), 500

@app.route('/api/delete-session', methods=['POST'])
def delete_session():
    """Delete a specific conversation session"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({
                'status': 'error',
                'message': 'session_id is required'
            }), 400
        
        filepath = Path(f'artifacts/conversations/{session_id}.json')
        
        if not filepath.exists():
            return jsonify({
                'status': 'error',
                'message': f'Session {session_id} not found'
            }), 404
        
        filepath.unlink()
        
        return jsonify({
            'status': 'success',
            'message': f'Session {session_id} deleted'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to delete session: {str(e)}'
        }), 500

@app.route('/api/new-session', methods=['POST'])
def new_session():
    """
    Start a new conversation session
    Resets both Iteration 1 and Iteration 2 agents
    """
    try:
        # Clear current session
        session.pop('session_id', None)
        
        # Reset GPT-4 agent if active
        if USE_GPT4_AGENT and elicitation_agent_v2:
            elicitation_agent_v2.reset()
        
        # Create new session
        session_id = conversation_manager.create_session()
        session['session_id'] = session_id
        
        return jsonify({
            'status': 'success',
            'session_id': session_id,
            'message': 'New session started successfully.',
            'agent': 'GPT4_v2' if USE_GPT4_AGENT else 'Ollama_v1'
        })
        
    except Exception as e:
        print(f"Error creating new session: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'An error occurred creating a new session.'
        }), 500


@app.route('/api/usage-stats', methods=['GET'])
def usage_stats():
    """
    Get token usage and cost statistics (Iteration 2 only)
    Returns error if GPT-4 agent not enabled
    """
    try:
        if USE_GPT4_AGENT and elicitation_agent_v2:
            stats = elicitation_agent_v2.get_usage_stats()
            return jsonify({
                'status': 'success',
                'stats': stats,
                'agent': 'GPT4_ElicitationAgent_v2'
            })
        else:
            return jsonify({
                'status': 'unavailable',
                'message': 'Token tracking only available with GPT-4 agent. Set USE_GPT4_AGENT=true and provide OPENAI_API_KEY.',
                'agent': 'Ollama_v1'
            })
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/session-info', methods=['GET'])
def session_info():
    """
    Get information about current session
    Includes requirements count and metadata
    """
    try:
        session_id = session.get('session_id')
        
        if not session_id:
            return jsonify({
                'status': 'error',
                'message': 'No active session'
            }), 404
        
        summary = conversation_manager.get_session_summary(session_id)
        
        return jsonify({
            'status': 'success',
            'session': summary,
            'agent': 'GPT4_v2' if USE_GPT4_AGENT else 'Ollama_v1'
        })
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint with agent status
    Shows which iteration is active
    """
    health_data = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'iteration': 2 if USE_GPT4_AGENT else 1,
        'agents': {
            'ollama_v1': {
                'available': ollama_client.check_connection(),
                'model': ollama_client.model
            },
            'gpt4_v2': {
                'enabled': USE_GPT4_AGENT,
                'available': elicitation_agent_v2 is not None,
                'model': elicitation_agent_v2.model if elicitation_agent_v2 else None
            }
        }
    }
    
    return jsonify(health_data)


if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("DEBUG", "true").lower() == "true"
    
    print("\n" + "="*60)
    print("Requirements Engineering Assistant")
    print("="*60)
    print(f"Running on: http://localhost:{port}")
    print(f"Iteration: {'2 (GPT-4 Multi-Agent)' if USE_GPT4_AGENT else '1 (Ollama Baseline)'}")
    
    if USE_GPT4_AGENT:
        print(f"Active Agent: GPT-4 ElicitationAgent")
        print(f"Model: {elicitation_agent_v2.model if elicitation_agent_v2 else 'N/A'}")
        print(f"Token Tracking:  Enabled")
    else:
        print(f"Active Agent: Ollama ElicitationEngine")
        print(f"Model: {ollama_client.model}")
        print(f"Token Tracking:  Not available")
    
    print(f"Fallback: Ollama (llama3.1:8b)")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=debug)