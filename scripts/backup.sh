#!/usr/bin/env bash
# Back up the production EIL database and object-store volume.
#
# Usage:
#   ./scripts/backup.sh
#   BACKUP_DIR=/mnt/backups RETENTION_DAYS=30 ./scripts/backup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="infra/compose/docker-compose.prod.yml"
ENV_FILE="${ENV_FILE:-.env.prod}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Copy .env.prod.example and fill it in." >&2
  exit 1
fi

COMPOSE=(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE")
mkdir -p "$BACKUP_DIR"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
db_file="$BACKUP_DIR/eil-db-$stamp.dump"
objects_file="$BACKUP_DIR/eil-objects-$stamp.tar.gz"

echo "[backup] database -> $db_file"
"${COMPOSE[@]}" exec -T postgres pg_dump -U eil -d eil --format=custom > "$db_file"

echo "[backup] objects  -> $objects_file"
"${COMPOSE[@]}" exec -T api tar czf - -C /data/objects . > "$objects_file"

echo "[backup] removing backups older than $RETENTION_DAYS days"
find "$BACKUP_DIR" -maxdepth 1 -type f \
  \( -name 'eil-db-*.dump' -o -name 'eil-objects-*.tar.gz' \) \
  -mtime +"$RETENTION_DAYS" -delete

echo "[backup] done"
ls -lh "$db_file" "$objects_file"
