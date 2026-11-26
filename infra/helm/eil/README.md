# EIL API Helm chart — plan Phase 9, T9.7

Deploys the EIL API (`eil-api`) on Kubernetes with PostgreSQL.

## Install

```sh
helm install eil ./infra/helm/eil -n eil --create-namespace \
  --set postgres.password=<strong>            # never commit secrets
```

The chart deploys the API from the pre-built image (`eil-api:0.1.0` —
`apps/api/Dockerfile`). Secrets (`DEV_JWT_SECRET`, `OIDC_CLIENT_SECRET`,
`GROQ_API_KEY`, `GRAPH_CLIENT_SECRET`, object-store keys) are read from the
`<release>-secrets` Secret by the deployment; `values.yaml`'s
`secrets.*` fields are optional conveniences.

## Configuration (values.yaml)

| Group | Notes |
|---|---|
| `env` | API env vars (`APP_ENV=prod`, `AUTH_MODE=oidc`, `CORS_ORIGINS`, `TRUSTED_HOSTS`, rate limits…) — see `eil/core/config.py`. Outside `local`/`ci`/`demo`, `TRUSTED_HOSTS` and `CORS_ORIGINS` must be set (Settings fails closed, plan §13.3). |
| `secrets` | Secret values. Prefer managing them with sealed-secrets or `helm upgrade --set-file`-based flows. |
| `postgres` | `DATABASE_URL` built from `user/password/host/port/database` — set a strong password. |
| `service`, `ingress` | Expose the API; TLS via an ingress cert. |
| `resources`, `probes` | Requests/limits and `/healthz` + `/readyz` probes. |

## Prerequisites

- PostgreSQL (or the app falls back to SQLite — not recommended in prod; set
  `DATABASE_URL` accordingly and drop the postgres block).
- MinIO + cert-manager if using object storage / TLS (`OBJECT_STORE_*` env).
- Keycloak realm `eil` (compose: `infra/compose/docker-compose.yml`) —
  MFA actions per plan §13.1.

## Security notes (plan §13.3)

- `TRUSTED_HOSTS` must not be `*` outside dev/ci/demo.
- `CORS_ORIGINS` must be the web origin(s), never `*`.
- The chart does not deploy an OIDC IdP — run Keycloak separately and set
  `OIDC_ISSUER_URL` / `OIDC_CLIENT_ID_WEB` / `OIDC_AUDIENCE` via `env`.
