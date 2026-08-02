#!/bin/zsh

set -e

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

echo "PubMed PDF Library Sync"
echo "Working directory: $SCRIPT_DIR"
echo ""

if [ ! -d ".venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "Installing/updating dependencies..."
python -m pip install -r requirements.txt

echo ""
echo "Matching PDFs, renaming files, and updating CSV files..."
python -m src.main --sync-library

echo ""
echo "Finished."
echo "Press Enter to close this window."
read
