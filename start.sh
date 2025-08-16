#!/bin/bash

# Startup script for the FastAPI Question Answering Application

echo "🚀 Starting FastAPI Question Answering Application"
echo "=================================================="

# Check if virtual environment is activated
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo "✓ Virtual environment is active: $VIRTUAL_ENV"
else
    echo "⚠️  Virtual environment not detected. Consider using one."
fi

# Check if .env file exists
if [ -f ".env" ]; then
    echo "✓ Environment file (.env) found"
else
    echo "⚠️  No .env file found. Copy .env.example to .env and add your Gemini API key"
    echo "   cp .env.example .env"
fi

# Check if dependencies are installed
echo "📦 Checking dependencies..."
python -c "import fastapi, langchain_google_genai, pandas, matplotlib" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✓ All dependencies are installed"
else
    echo "❌ Missing dependencies. Run: pip install -r requirements.txt"
    exit 1
fi

# Start the application
echo "🌐 Starting server on http://localhost:8000"
echo "📝 API endpoint: http://localhost:8000/api/"
echo "📋 Health check: http://localhost:8000/"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

uvicorn main:app --reload --host 0.0.0.0 --port 8000
