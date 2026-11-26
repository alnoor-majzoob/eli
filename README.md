# EIL — Enterprise Execution Intelligence Layer

AI-assisted orchestration and intelligence layer for enterprise work, resource and
execution management (OQ RPI reference context).

> **Demo-grade, synthetic data only.** Simulated systems and synthetic models are
> labelled `SIM` / `SYNTHETIC` in the UI. AI proposes; humans dispose. See the
> implementation plan in `OQ_RPI_EIL_Implementation_Plan.md`.

## Status

Phase 0 — foundation and platform skeleton implemented and verified in local
(no-Docker) mode. See `docs/PROGRESS.md` for task status and honest limitations.

## Local quickstart (no Docker)

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Node ≥ 22.12, pnpm 11.

```bash
corepack enable pnpm          # if pnpm is not already on PATH
cp .env.example .env          # local fallbacks: SQLite, dev auth, inline jobs
make setup                    # uv sync + pnpm install
make migrate                  # create .data/eil.db and the baseline schema
make dev                      # API on :8000, web on :5173
```

Open http://localhost:5173 and sign in with the dev role selector (local mode only).
The API docs are at http://localhost:8000/docs and metrics at `/metrics`.

Useful targets:

```bash
make check       # lint + typecheck + tests
make test        # pytest + vitest
make build       # production web build
make e2e         # Playwright smoke tests (needs browser binaries)
make openapi     # regenerate OpenAPI + TypeScript client
```

## Full stack (Docker)

```bash
cp .env.example .env
# compose overrides DATABASE_URL/REDIS_URL/AUTH_MODE internally
make up
```

| Service       | URL                   |
| ------------- | --------------------- |
| Web           | http://localhost:3000 |
| API           | http://localhost:8000 |
| Keycloak      | http://localhost:8080 |
| Grafana       | http://localhost:3001 |
| Prometheus    | http://localhost:9090 |
| MinIO console | http://localhost:9001 |
| Mailpit       | http://localhost:8025 |
| OTLP gRPC     | http://localhost:4317 |

The stack includes PostgreSQL 16 + pgvector, Redis 7, MinIO, Keycloak (realm
`eil`, user `aisha` / `demo-password`), Mailpit, OTel collector, API, Celery
worker/beat and an nginx-served SPA. It is authored and YAML-validated but has
not been booted on this workstation because Docker is not installed.

## VPS deployment (direct ports)

For a single-VPS deployment with unique host ports, no Caddy/nginx reverse proxy
and demo authentication, see [`docs/deployment-vps.md`](docs/deployment-vps.md).

## Repository layout

```
apps/api        FastAPI modular monolith (Python 3.12)
apps/web        React + Vite SPA (TypeScript, Tailwind, i18next EN/AR)
apps/mocks      System simulators (Phase 3)
packages        Generated API client + shared types
connectors      Connector SDK and concrete connectors (Phase 3)
infra           Docker, compose, Keycloak realm, nginx, Grafana, OTel
seed            Synthetic data generators and replay cassettes
docs            ADRs, progress, design notes, runbooks
```

## Principles

- `AI_ENABLED=false` leaves the platform fully usable (manual capture, no suggestions).
- LLM output is never authoritative: deterministic engines compute every number;
  the model narrates or proposes, and a human accepts/rejects.
- Every AI-derived value carries provenance (source, quote, model, prompt version).
- Systems of record stay authoritative; integrations are read-only by default.
- Simulated systems and synthetic-trained models are visibly labelled.

## Configuration

All behaviour is configured through environment variables (`.env.example`) or, from
later phases, database configuration tables. Secrets are never committed.
