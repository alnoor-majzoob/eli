# ADR-002 — Local development fallbacks (no Docker)

- **Status:** Accepted (temporary; revisit when Docker/PostgreSQL are available)
- **Date:** 2026-11-20
- **Context:** The plan mandates PostgreSQL 16 + pgvector (ADR-05), Celery + Redis
  (ADR-06) and Keycloak OIDC (ADR-07). The build workstation has no Docker,
  PostgreSQL, Redis or Keycloak and no passwordless sudo. Development and CI for
  the fallback path must still be possible, and architecture must stay production-shaped.

## Decision

Introduce a runtime mode selected by configuration; the mandated stack remains the
target for `compose`/`demo` deployments.

| Concern        | Target (plan)            | Local fallback                                                                                                                  |
| -------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| Database       | PostgreSQL 16 + pgvector | SQLite via `aiosqlite` (`DATABASE_URL` default); dialect-aware SQLAlchemy types; Alembic guards Postgres-only DDL               |
| Jobs           | Celery + Redis + Beat    | Inline outbox dispatcher in the API process; Celery app scaffolded and `task_always_eager` when `REDIS_URL` is empty            |
| Identity       | Keycloak OIDC + MFA      | `AUTH_MODE=dev`: locally signed short-lived HS256 JWT via a dev-only endpoint; OIDC/JWKS verification code path kept and tested |
| Object storage | MinIO/S3                 | Local filesystem under `.data/objects` behind an `ObjectStore` interface                                                        |
| Semantics      | pgvector HNSW            | Python-side cosine similarity behind a `VectorSearch` interface (Phase 4)                                                       |
| Graph queries  | Postgres recursive CTEs  | SQLite supports recursive CTEs; service layer stays SQL-standard                                                                |

`APP_ENV=local` defaults to the fallbacks. Compose and CI use PostgreSQL; CI also
runs the SQLite path to catch divergence. Fallbacks are never silently presented as
the production integration: `docs/PROGRESS.md` and the capability matrix list them.

## Consequences

- Anyone can run `make dev` with only Python/uv and Node/pnpm.
- Schema must remain portable. Postgres-only features (extensions, `JSONB`,
  `VECTOR`, partial indexes, enums via `CREATE TYPE`) are handled per-dialect.
- The local fallback has fewer guarantees (no DB-level RLS, weaker concurrency,
  no pgvector recall benchmarking). These are recorded as known limitations.
- Before any client-facing demo on the full stack, `make up` must be exercised on a
  Docker-capable host and this ADR updated.
