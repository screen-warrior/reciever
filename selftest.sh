#!/usr/bin/env bash
# Quick local self-test for the receiver.
#
# Verifies (1) the HTTP server responds and (2) keystroke injection works by
# typing a sample line into whatever window you focus during the countdown.
#
# Usage:
#   bash selftest.sh
#   KB_TOKEN=your-token HOST=127.0.0.1 PORT=8765 bash selftest.sh
#
# Tip: run it, then quickly click into TextEdit (or any text field) before the
# countdown ends so you can watch it type.

set -u

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8765}"
TOKEN="${KB_TOKEN:-change-me-local-token}"
BASE="http://${HOST}:${PORT}"

echo "== 1. Health check =="
curl -s "${BASE}/health"; echo
echo

echo "== 2. Type test =="
echo "Focus a text field (e.g. TextEdit) within 4 seconds..."
curl -s -X POST "${BASE}/type" \
  -H "x-token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello from the Mac receiver!\n","start_delay":4}'
echo
echo
echo "If the sample text appeared in your focused window, the receiver is fully working."
