#!/usr/bin/env bash
# Playwright API server: isolated SQLite database, migrations, uvicorn.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p .data
rm -f .data/e2e.db

export APP_ENV=local
export AUTH_MODE=dev
export AI_ENABLED=false
export LLM_MODE=replay
export OUTBOX_INLINE_DISPATCHER=true
export DATABASE_URL="sqlite+aiosqlite:///$ROOT/.data/e2e.db"
export OBJECT_STORE_LOCAL_DIR="$ROOT/.data/objects"
export CORS_ORIGINS='["http://127.0.0.1:5174","http://localhost:5174"]'
export LOG_FORMAT=console
export LOG_LEVEL=WARNING

cd apps/api
uv run alembic upgrade head
exec uv run uvicorn eil.asgi:app --host 127.0.0.1 --port 8010
