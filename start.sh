#!/bin/bash
# Startup script for AI Sales Coach

echo "🚀 Starting AI Sales Coach Application"
echo "========================================"
echo ""

# Activate virtual environment
if [ -d ".venv" ]; then
    echo "✅ Activating virtual environment..."
    source .venv/bin/activate
else
    echo "❌ Virtual environment not found. Please run: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found. Please create it from .env.example"
    exit 1
fi

echo "✅ Environment configured"
echo ""

# Start the server
echo "🌐 Starting server on http://localhost:8000"
echo "   Press CTRL+C to stop"
echo ""

python -m src.main
