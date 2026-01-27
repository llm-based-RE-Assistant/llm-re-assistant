"""
LLM-Based Requirements Engineering Assistant
Flask Application Entry Point
"""

from flask import Flask, render_template, request, jsonify, session
from datetime import datetime
import os
from src.utils.ollama_client import OllamaClient
from src.utils.conversation_manager import ConversationManager
from src.elicitation.elicitation_engine import ElicitationEngine
from src.agents.validation_agent import ValidationAgent
from src.integration.validation_bridge import ValidationBridge

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Initialize components
ollama_client = OllamaClient(model="llama3.1:8b")
conversation_manager = ConversationManager()
elicitation_engine = ElicitationEngine(ollama_client)
validation_agent = ValidationAgent()
validation_bridge = ValidationBridge(validation_agent, conversation_manager)

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
    """Handle chat messages from user"""
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({
                'status': 'error',
                'response': 'Please provide a message.'
            }), 400
        
        session_id = session.get('session_id')
        if not session_id:
            session_id = conversation_manager.create_session()
            session['session_id'] = session_id
        
        conversation_manager.add_message(session_id, 'user', user_message)
        conversation_history = conversation_manager.get_conversation(session_id)
        
        assistant_response = elicitation_engine.process_message(
            user_message, 
            conversation_history
        )
        
        conversation_manager.add_message(session_id, 'assistant', assistant_response)
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
    """Generate IEEE-830 specification draft from conversation history"""
    try:
        session_id = session.get('session_id')
        
        if not session_id:
            return jsonify({
                'status': 'error',
                'message': 'No active conversation session found.'
            }), 400
        
        conversation_history = conversation_manager.get_conversation(session_id)
        
        if len(conversation_history) < 2:
            return jsonify({
                'status': 'error',
                'message': 'Not enough conversation data to generate specification.'
            }), 400
        
        specification = elicitation_engine.generate_specification(conversation_history)
        
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
        session.pop('session_id', None)
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


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/validate-requirements', methods=['POST'])
def validate_requirements():
    """Validate all requirements in current conversation"""
    try:
        session_id = session.get('session_id')
        
        if not session_id:
            return jsonify({
                'status': 'error',
                'message': 'No active conversation session found.'
            }), 400
        
        result = validation_bridge.validate_conversation(session_id)
        
        if result['status'] == 'no_requirements':
            return jsonify({
                'status': 'warning',
                'message': result['message'],
                'requirements_found': 0
            })
        
        report_text = validation_bridge.format_validation_report_for_chat(
            result['report'],
            result['validated_requirements']
        )
        
        return jsonify({
            'status': 'success',
            'requirements_found': result['requirements_found'],
            'report': result['report'],
            'report_text': report_text,
            'validated_requirements': result['validated_requirements'],
            'extraction_method': result.get('extraction_method', 'keyword')
        })
        
    except Exception as e:
        print(f"Error validating requirements: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': 'An error occurred during validation.'
        }), 500


@app.route('/api/validation-summary', methods=['GET'])
def get_validation_summary():
    """Get validation summary for current session"""
    try:
        session_id = session.get('session_id')
        
        if not session_id:
            return jsonify({
                'status': 'error',
                'message': 'No active session.'
            }), 400
        
        summary = validation_bridge.get_validation_summary(session_id)
        
        if not summary:
            return jsonify({
                'status': 'not_validated',
                'message': 'Requirements have not been validated yet.'
            })
        
        return jsonify({
            'status': 'success',
            'summary': summary
        })
        
    except Exception as e:
        print(f"Error getting validation summary: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'An error occurred.'
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)