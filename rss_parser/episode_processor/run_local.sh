#!/bin/bash
# Run the episode processor locally for development.
# FAKE_MODE=1: no GPU, no GCS — writes JSON to ./output/ instead.
set -euo pipefail

export FAKE_MODE=1
export OUTPUT_DIR=output
export PORT=8080

echo "Starting episode processor locally (FAKE_MODE — no GPU, no GCS)…"
echo "Transcriptions will be written to ./output/"
echo ""
echo "Send test requests with:  ./test_local.sh"
echo ""
python3 main.py
