#!/bin/bash

# LLM-Based RE Assistant - Setup Script
# This script initializes the project structure and dependencies

echo "=========================================="
echo "LLM-Based RE Assistant - Iteration 1 MVP"
echo "Setup & Initialization Script"
echo "=========================================="
echo ""

# Check Python installation
echo "[1/7] Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo "❌ ERROR: Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo "✅ Found: $PYTHON_VERSION"
echo ""

# Create directory structure
echo "[3/7] Creating directory structure..."
mkdir -p artifacts/conversations
mkdir -p artifacts/specifications
mkdir -p docs
mkdir -p src/elicitation
mkdir -p src/modeling
mkdir -p src/specification
mkdir -p src/verification
mkdir -p src/utils
mkdir -p templates
mkdir -p tests
echo "✅ Directories created"
echo ""

# Create __init__.py files for Python packages
echo "[4/7] Creating Python package files..."
touch src/__init__.py
touch src/elicitation/__init__.py
touch src/modeling/__init__.py
touch src/specification/__init__.py
touch src/verification/__init__.py
touch src/utils/__init__.py
touch tests/__init__.py
echo "✅ Package files created"
echo ""

# Create virtual environment
echo "[5/7] Setting up virtual environment..."
if [ -d "venv" ]; then
    echo "⚠️  Virtual environment already exists. Skipping creation."
else
    python3 -m venv venv
    echo "✅ Virtual environment created"
fi
echo ""

# Activate virtual environment and install dependencies
echo "[6/7] Installing Python dependencies..."
if [ -f "venv/bin/activate" ]; then
    # Linux/Mac
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    echo "✅ Dependencies installed"
elif [ -f "venv/Scripts/activate" ]; then
    # Windows (Git Bash)
    source venv/Scripts/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    echo "✅ Dependencies installed"
else
    echo "⚠️  Could not find virtual environment activation script"
    echo "Please manually activate and run: pip install -r requirements.txt"
fi
echo ""

# Create .env file if it doesn't exist
echo "[7/7] Creating environment configuration..."
if [ ! -f ".env" ]; then
    cat > .env << EOF
# Flask Configuration
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
FLASK_ENV=development
FLASK_DEBUG=True

# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_API_KEY=add-your-api-key
EOF
    echo "✅ .env file created with random secret key"
else
    echo "⚠️  .env file already exists. Skipping creation."
fi
echo ""

# Final instructions
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Ensure Ollama is running:"
echo "   $ ollama serve"
echo ""
echo "2. Activate virtual environment:"
echo "   $ source venv/bin/activate    # Linux/Mac"
echo "   $ venv\\Scripts\\activate      # Windows"
echo ""
echo "3. Run the application:"
echo "   $ python app.py"
echo ""
echo "4. Open browser and navigate to:"
echo "   http://localhost:5000"
echo ""
echo "=========================================="
echo "Happy Requirements Engineering! 🚀"
echo "=========================================="
