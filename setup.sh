#!/bin/bash

# AI Sales Coach - Quick Setup Script

echo "🎯 AI Sales Coach - Setup Script"
echo "================================"
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Found Python $python_version"
echo ""

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Copy .env.example to .env"
echo "   cp .env.example .env"
echo ""
echo "2. Edit .env and add your Azure credentials:"
echo "   - FOUNDRY_ENDPOINT (from ai.azure.com)"
echo "   - SPEECH_KEY (from Azure Speech Service)"
echo "   - SPEECH_REGION (e.g., eastus2)"
echo ""
echo "3. Run the application:"
echo "   python src/main.py"
echo ""
echo "4. Open browser to http://localhost:8000"
echo ""
echo "See README.md and DEPLOYMENT.md for detailed instructions."
