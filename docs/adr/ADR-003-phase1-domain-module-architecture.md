# ADR-003 — Phase 1 domain module architecture

- **Status:** Accepted
- **Date:** 2026-11-21
- **Context:** Phase 1 deliverables in the implementation plan: RBAC/ABAC with SoD, hash-chained append-only audit, core execution entities with a parent/type/cycle-safe state machine, data-driven governance workflows with approvals/SLA/delegation, per-scope dashboards, contract-first web modules, and a Keycloak realm. The plan's authoritative sources are `OQ_RPI_EIL_Implementation_Plan.md` (§7 schema, §10 phases, §11 scenarios, §13 matrix, scenario flows).

## Decision

Implement a service/router/schemas split per domain (`identity`, `execution`, `governance`, `audit`) plus `seed_data.py` as the data-driven permission/workflow catalogue. Enforce permission scopes with SQLAlchemy models and a thin ABAC helper; workflows are rows + definitions, not hard-coded state machines. The append-only audit hash chain is appended by SQL triggers and verified by `GET /api/v1/audit/verify`; export/filters/CSV use the same service functions.

Dashboards consume `PermissionContext` and are scope-filtered (`_scoped`) except global admins, avoiding N+1 by counting in SQL. Web modules are React Query + typed wrappers from the generated OpenAPI client; navigation covers Phase 1 workspace and governance modules. OIDC/OIDC-MFA fallback to dev auth per ADR-002 until Keycloak deployment is exercised.

## Consequences

- The plan's matrix can be changed by editing `seed_data.ROLE_PERMISSIONS`; no code drift between matrix and enforcement.
- Append-only triggers prevent tests from hiding tampering, so verification uses DB triggers and unit tests; production deployments run migrations before `uvicorn`.
- Phase 2 can add collectors/metrics and policy enforcers without changing Phase 1 module boundaries.

## Verification

- `make check` gates: backend pytest, web vitest, ESLint/Prettier/tsc, backend ruff/mypy, OpenAPI client regeneration.
- Phase 1 exit flow: objective → initiative/key result → demand → submit → approver decision → audit verify; `test_phase1_exit.py`.
