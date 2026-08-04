#!/usr/bin/env bash
# Start Knowledge OS API + public tunnel for manual testing.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src
export ENVIRONMENT=development
export USE_DEV_EMBEDDINGS=true

TMUX_CONF="-f /exec-daemon/tmux.portal.conf"
API_SESSION="knowledge-os-api"
TUNNEL_SESSION="knowledge-os-tunnel"
LOG="/tmp/knowledge-os-tunnel.log"
CREDS="/tmp/knowledge-os-demo.json"

echo "==> Migrating database..."
python3 -m alembic upgrade head
python3 scripts/ensure_platform_workspace.py

echo "==> Seeding demo workspace..."
python3 scripts/deploy_demo.py 2>/dev/null | grep -A20 '^{' > "$CREDS" || python3 scripts/deploy_demo.py > "$CREDS"

if ! curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
  echo "==> Starting API server..."
  tmux $TMUX_CONF kill-session -t "=$API_SESSION" 2>/dev/null || true
  tmux $TMUX_CONF new-session -d -s "$API_SESSION" -c "$PWD" -- "${SHELL:-bash}" -l
  tmux $TMUX_CONF send-keys -t "$API_SESSION:0.0" \
    "export PYTHONPATH=src ENVIRONMENT=development USE_DEV_EMBEDDINGS=true; python3 -m uvicorn knowledge_os.api.app:app --host 0.0.0.0 --port 8000" C-m
  for i in $(seq 1 20); do
    curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1 && break
    sleep 1
  done
else
  echo "==> API already running on :8000"
fi

echo "==> Starting public tunnel..."
tmux $TMUX_CONF kill-session -t "=$TUNNEL_SESSION" 2>/dev/null || true
tmux $TMUX_CONF new-session -d -s "$TUNNEL_SESSION" -c "$PWD" -- "${SHELL:-bash}" -l
tmux $TMUX_CONF send-keys -t "$TUNNEL_SESSION:0.0" \
  "rm -f '$LOG'; npx -y cloudflared tunnel --url http://127.0.0.1:8000 2>&1 | tee '$LOG'" C-m

PUBLIC_URL=""
for i in $(seq 1 30); do
  PUBLIC_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" 2>/dev/null | tail -1 || true)
  if [ -n "$PUBLIC_URL" ]; then
    curl -sf --max-time 8 "${PUBLIC_URL}/health" >/dev/null 2>&1 && break
    PUBLIC_URL=""
  fi
  sleep 2
done

if [ -z "$PUBLIC_URL" ]; then
  echo "==> Cloudflare tunnel unavailable, trying localtunnel..."
  tmux $TMUX_CONF kill-session -t "=$TUNNEL_SESSION" 2>/dev/null || true
  tmux $TMUX_CONF new-session -d -s "$TUNNEL_SESSION" -c "$PWD" -- "${SHELL:-bash}" -l
  tmux $TMUX_CONF send-keys -t "$TUNNEL_SESSION:0.0" \
    "rm -f '$LOG'; npx -y localtunnel --port 8000 2>&1 | tee '$LOG'" C-m
  for i in $(seq 1 20); do
    PUBLIC_URL=$(grep -oE 'https://[a-z0-9-]+\.loca\.lt' "$LOG" 2>/dev/null | tail -1 || true)
    if [ -n "$PUBLIC_URL" ]; then break; fi
    sleep 2
  done
fi

if [ -z "$PUBLIC_URL" ]; then
  echo "ERROR: Tunnel URL not ready. Check: tmux attach -t $TUNNEL_SESSION"
  exit 1
fi

echo ""
echo "=============================================="
echo "  Knowledge OS — LIVE"
echo "=============================================="
echo "  UI:    ${PUBLIC_URL}/ui/"
echo "  Docs:  ${PUBLIC_URL}/docs"
echo "  API:   ${PUBLIC_URL}/api/v1"
echo "=============================================="
echo ""
echo "Credentials ($(basename "$CREDS")):"
cat "$CREDS"
echo ""
echo "Tunnel log: $LOG"
