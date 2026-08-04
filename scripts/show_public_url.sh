#!/usr/bin/env bash
# Print the current public tunnel URL (if cloudflared quick tunnel is running).
set -euo pipefail
LOG="${TMPDIR:-/tmp}/knowledge-os-tunnel.log"
if [ -f "$LOG" ]; then
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | tail -1)
  if [ -n "$URL" ]; then
    echo "Public UI: ${URL}/ui/"
    echo "API docs:  ${URL}/docs"
    exit 0
  fi
fi
echo "No active tunnel found. Start with: npx cloudflared tunnel --url http://127.0.0.1:8000"
exit 1
