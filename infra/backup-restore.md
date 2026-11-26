# Backup & restore — EIL (plan Phase 9, T9.7)

Backup procedure for the EIL deployment (SQLite/PostgreSQL + object storage +
audit trail). RPO/RTO expectations: see [DR notes](./dr-notes.md).

## What to back up

| Data | Where | Backup method |
|---|---|---|
| Application database | PostgreSQL (`DATABASE_URL`) | `pg_dump --format=custom eil > eil-$(date +%F).dump` (or `pg_dump -Fc`); SQLite fallback: `cp eil.db` while stopped |
| Object store (artifacts) | MinIO/S3 (`OBJECT_STORE_BUCKET`) | `mc cp` / `aws s3 sync s3://eil-artifacts backup/objects` |
| Audit log | Same DB as application data (`audit_log` table) — covered by the DB dump | dump |
| Config | `values.yaml` + `secrets.*` — keep under version control with `sops`/`sealed-secrets` or managed elsewhere | `git` |

## Restore procedure

1. Stop the API pod (`kubectl scale deploy/<release>-eil-api --replicas=0`).
2. Restore the DB: `pg_restore eil-YYYY-MM-DD.dump -d eil` (or copy the SQLite file back and restart).
3. Restore objects: `aws s3 sync backup/objects s3://eil-artifacts` (or `mc cp -r`).
4. Verify: `helm upgrade <release> ./infra/helm/eil` (RUN_MIGRATIONS=1 applies pending migrations), then run the audit-trail verification script (`scripts/` — `audit verify` per plan §1.3) and confirm the `/healthz` + `/readyz` probes pass.

## Automation (suggested)

Cron/backup job:

```sh
#!/bin/sh
# Daily backup: dump DB, sync object store, copy the dump offsite.
set -eu
ts=$(date +%F)
pg_dump -h "$PGHOST" -U eil -d eil -Fc -f /backup/eil-$ts.dump
aws s3 sync s3://eil-artifacts /backup/objects || true
```

Note: with `LLM_MODE=replay` cassettes (`seed/cassettes`) are source-controlled —
back up the repository as well for full fidelity.
