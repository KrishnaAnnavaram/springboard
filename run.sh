#!/bin/bash
set -e

echo "========================================="
echo "  Springboard - Job Automation Setup"
echo "========================================="

# Check Python version
PYTHON_CMD=""
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "ERROR: Python not found. Please install Python 3.10+."
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
echo "Found Python: $PYTHON_VERSION"

# Check Git
if ! command -v git &>/dev/null; then
    echo "WARNING: Git not found. Version control unavailable."
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt --quiet

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env from template..."
    cp .env.example .env
    echo "IMPORTANT: Edit .env with your credentials before running."
fi

# Create data directories
mkdir -p data/profiles data/resumes data/screenshots data/logs data/backups

# Initialize database
echo "Initializing database..."
$PYTHON_CMD -m src.database.init_db

echo ""
echo "========================================="
echo "  Setup complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Edit .env with your LinkedIn and API credentials"
echo "  2. Run: streamlit run src/dashboard/app.py"
echo ""

# Start Streamlit if --start flag is passed
if [[ "$1" == "--start" ]]; then
    echo "Starting Streamlit dashboard..."
    streamlit run src/dashboard/app.py --server.port 8501
fi
