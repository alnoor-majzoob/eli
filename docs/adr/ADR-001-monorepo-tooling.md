# ADR-001 — Monorepo and tooling baseline

- **Status:** Accepted
- **Date:** 2026-11-20
- **Context:** The implementation plan (§3, §6) mandates a monorepo with a React
  (Vite) SPA and a Python FastAPI modular monolith, plus shared generated types.

## Decision

- One repository. pnpm workspaces for JavaScript/TypeScript (`apps/web`,
  `packages/*`); a `uv` project for the API at `apps/api`.
- TypeScript strict, ESLint + Prettier, ruff + mypy on core modules.
- Conventional Commits enforced via commitlint; pre-commit runs ruff, mypy,
  ESLint and Prettier.
- Generated OpenAPI client lives in `packages/api-client` and is committed; CI
  fails on drift.
- Repo root is the project directory itself (`/home/alnoor/projects/eli`), not a
  nested `eil/` directory.

## Consequences

- Atomic cross-cutting changes and a single CI pipeline.
- Contributors need Python 3.12 + uv and Node ≥ 22.12 + pnpm 11.
- Generated artefacts must be regenerated whenever the API contract changes.
