#!/usr/bin/env bash
# Start Knowledge OS API for manual testing (local or tunneled).
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src
export ENVIRONMENT=development
export USE_DEV_EMBEDDINGS=true

python3 -m alembic upgrade head
python3 scripts/ensure_platform_workspace.py
python3 scripts/deploy_demo.py > /tmp/knowledge-os-demo.json

echo "=== Demo credentials saved to /tmp/knowledge-os-demo.json ==="
cat /tmp/knowledge-os-demo.json

exec python3 -m uvicorn knowledge_os.api.app:app --host 0.0.0.0 --port 8000
