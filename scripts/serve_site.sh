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
if [[ -z "$IP_ADDR" ]]; then
  IP_ADDR="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
fi
if [[ -z "$IP_ADDR" ]]; then
  IP_ADDR="$(ip route get 1.1.1.1 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}' || true)"
fi

echo "Serving from: $ROOT_DIR"
echo "Local URL: http://localhost:${PORT}/docs/"
if [[ -n "$IP_ADDR" ]]; then
  echo "Phone URL: http://${IP_ADDR}:${PORT}/docs/"
else
  echo "Phone URL: unable to detect network IP automatically."
fi
echo "Press Ctrl+C to stop."

python3 -m http.server "$PORT"
