#!/bin/zsh

set -e

SCRIPT_DIR="${0:A:h}"
exec "$SCRIPT_DIR/run_pubmed_pdf_downloader.command" --clipboard
