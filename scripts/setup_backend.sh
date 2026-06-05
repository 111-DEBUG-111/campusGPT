#!/bin/bash
# CampusGPT Backend Quick Setup Script for macOS
# Run from the project root: bash scripts/setup_backend.sh

set -e

echo "🎓 CampusGPT Backend Setup"
echo "=========================="

# Check Python version
PYTHON=$(which python3.11 2>/dev/null || which python3 2>/dev/null)
if [ -z "$PYTHON" ]; then
  echo "❌ Python 3.11+ is required. Install with: brew install python@3.11"
  exit 1
fi

PYTHON_VERSION=$($PYTHON --version 2>&1 | cut -d' ' -f2)
echo "✓ Using Python $PYTHON_VERSION"

# Create venv
cd backend
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  $PYTHON -m venv .venv
fi

# Activate
source .venv/bin/activate

# Install deps
echo "Installing Python dependencies (this may take a few minutes)..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# Create .env if missing
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "⚠️  Created backend/.env from template."
  echo "   Please fill in: GEMINI_API_KEY, QDRANT_URL, QDRANT_API_KEY, ADMIN_API_KEY"
fi

# Create data directories
mkdir -p data/uploads

echo ""
echo "✅ Backend setup complete!"
echo ""
echo "To start the backend:"
echo "  cd backend"
echo "  source .venv/bin/activate"
echo "  uvicorn app.main:app --reload"
