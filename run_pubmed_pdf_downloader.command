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
  echo ""
  echo "Enter your email address to enable Unpaywall for this run."
  echo "Leave blank and press Enter to skip Unpaywall."
  printf "Email: "
  read EMAIL_INPUT
  if [ -n "$EMAIL_INPUT" ]; then
    export UNPAYWALL_EMAIL="$EMAIL_INPUT"
  fi
  echo ""
fi

echo "Starting download..."
if [ "$#" -gt 0 ]; then
  python -m src.main "$@"
else
  python -m src.main input/pmids.txt
fi

echo ""
echo "Finished."
echo "Press Enter to close this window."
read
