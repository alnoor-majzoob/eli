#!/usr/bin/env bash
set -euo pipefail

if [[ "${RUN_MIGRATIONS:-0}" == "1" ]]; then
  echo "[entrypoint] applying database migrations"
  alembic upgrade head
fi

exec "$@"
