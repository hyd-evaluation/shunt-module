#!/bin/bash
# install.sh - Simple one-command installer for shunt-module

set -e

echo "Installing shunt-module..."

# 1. Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found. Install Python 3.11+ first."
    exit 1
fi

# 2. Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# 4. Test
echo "Testing setup..."
python3 -c "from worker import ShuntWorker; print('✅ Shunt module ready!')"

echo ""
echo "✅ Setup complete!"
echo "Run: python3 run_evals.py"
