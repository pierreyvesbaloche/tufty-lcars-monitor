#!/bin/bash
set -e

echo "=== Host Environment Setup ==="

# 1. Update system packages
sudo apt update
sudo apt install -y python3-venv python3-pip

# 2. Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# 3. Activate and upgrade pip
source .venv/bin/activate
pip install --upgrade pip

# 4. Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

echo ""
echo "=== Setup completed successfully! ==="
echo "To run the script:"
echo "  source .venv/bin/activate"
echo "  python host/sender.py"

