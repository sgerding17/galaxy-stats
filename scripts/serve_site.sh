#!/usr/bin/env bash
# AUTOGENTERATED BY CODEX: edit with care.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8000}"

cd "$ROOT_DIR"
python3 scripts/build_site.py

IP_ADDR="$(ipconfig getifaddr en0 2>/dev/null || true)"
if [[ -z "$IP_ADDR" ]]; then
  IP_ADDR="$(ipconfig getifaddr en1 2>/dev/null || true)"
fi

echo "Serving from: $ROOT_DIR"
echo "Local URL: http://localhost:${PORT}/stats/"
if [[ -n "$IP_ADDR" ]]; then
  echo "Phone URL: http://${IP_ADDR}:${PORT}/stats/"
else
  echo "Phone URL: unable to detect network IP automatically."
fi
echo "Press Ctrl+C to stop."

python3 -m http.server "$PORT"
