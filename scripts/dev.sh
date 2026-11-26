#!/usr/bin/env bash
# Local development runner: API (uvicorn) + web (vite), no Docker required.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "[dev] .env not found — copying .env.example (local fallbacks)."
  cp .env.example .env
fi

cleanup() {
  echo "[dev] shutting down..."
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null || true
  [[ -n "${WEB_PID:-}" ]] && kill "$WEB_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

mkdir -p .data
(cd apps/api && uv run alembic upgrade head)

echo "[dev] API   http://localhost:8000  (docs: /docs)"
(cd apps/api && uv run uvicorn eil.asgi:app --reload --host 0.0.0.0 --port 8000) &
API_PID=$!

echo "[dev] Web   http://localhost:5173"
pnpm --filter @eil/web dev &
WEB_PID=$!

wait -n "$API_PID" "$WEB_PID"
