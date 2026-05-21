#!/bin/zsh

set -e

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

echo "PubMed PDF Downloader"
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
if [ -z "$UNPAYWALL_EMAIL" ]; then
  echo "UNPAYWALL_EMAIL is not set."
  echo "PMC PDF download will still be tried, but Unpaywall search will be skipped."
  echo "To enable Unpaywall, run this in Terminal before launching:"
  echo '  export UNPAYWALL_EMAIL="your-email@example.com"'
  echo ""
fi

echo "Starting download..."
python -m src.main input/pmids.txt

echo ""
echo "Finished."
echo "Press Enter to close this window."
read

