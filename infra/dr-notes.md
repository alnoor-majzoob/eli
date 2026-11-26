# Disaster recovery notes — EIL (plan Phase 9, T9.7)

Derived from the business impact of the EIL components; refresh after any
architecture change.

## Critical path (order of impact)

1. **API (eil-api)** — serves the web UI and all integrations; down → no new
   work items, no automation.
2. **PostgreSQL (`eil` DB)** — the source of truth for the work graph, audit
   trail and AI suggestions; the DB is append-only by policy (audit) —
   protects against silent tampering but not data loss.
3. **Object storage (MinIO/S3, `eil-artifacts`)** — source artifacts + canonical
   payloads; down → new artifact ingestion fails (sync runs log errors).
4. **Simulators (apps/mocks)** — demo-only; no production impact.
5. **AI gateway** — provider (Groq) down → AI suggestions stop; deterministic
   engine + approvals still work (R12, graceful degradation).

## RTO / RPO targets (demo-grade, from plan §9/§13/§14)

| Tier | Target | Notes |
|---|---|---|
| Critical (API + DB) | RTO: 4h, RPO: 1h | DB dump + object store sync; audit trail retained |
| Optional (simulators, AI gateway) | RTO: 24h, RPO: none | Simulators are ephemeral demo tools; Groq down only stops AI suggestions |

## Data loss risk scenarios

- **DB corruption** — hash-chained audit trail detects tampering but not loss;
  offsite dumps (see [backup-restore.md](./backup-restore.md)) are the
  protection.
- **Audit log loss** — append-only by design (no update/delete API); SQLite
  file copy while stopped.
- **Secrets loss** — documented in the Helm chart README; rotated secrets
  require re-configuration of OIDC/Groq/MinIO clients at the IdP/provider.

## Drills

- **Table test**: `pg_dump` → restore to a fresh cluster → `alembic upgrade head`
  → `GET /api/v1/healthz` + `/readyz` pass; compare audit hash chain tail with
  `scripts/verify_audit` (TODO — see PROGRESS honest list: nightly verification).
- **Network isolation**: point `OBJECT_STORE_ENDPOINT` at an unreachable host —
  ingestion errors are logged per record (sync run errors), the platform
  stays up (R12).

## Cross-team impact

- Keycloak realm `eil` — users/groups/MFA actions (Phase 1, T1.8).
- External systems of record (P6/EAM/ERP/HR) — connector syncs are idempotent
  via `sync_cursor`; conflicts are logged (SOD-4).
