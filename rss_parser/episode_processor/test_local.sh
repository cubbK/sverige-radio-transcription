#!/bin/bash
# Send a test episode to the locally running episode processor.
set -euo pipefail

URL="http://localhost:8080"

curl -s -X POST "${URL}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Episode",
    "description": "A short test",
    "guid": "test-guid-001",
    "pub_date": "2026-01-01",
    "mp3_url": "https://sr-restored.se/rss/5466/sample.mp3"
  }' | cat

echo ""
