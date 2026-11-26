# EIL — User Manual (English)

A detailed guide to the EIL platform (Enterprise Execution Intelligence Layer):
the pages, the data model, the roles, and how to use each feature.

---

## 1. Introduction

EIL is an enterprise execution intelligence layer that puts AI work intelligence
on top of systems of record. It delivers:

- **Strategic outcomes**: objectives, key results, benefits, commitments and
  projects (the work graph).
- **Demand-to-delivery**: demand submission → prioritisation board → automatic
  conversion to programs/projects.
- **Prioritisation**: a deterministic scoring engine with explainable
  breakdowns, overrides (SoD-2) and an AI-assisted scoring flow.
- **Capacity & what-if**: resource allocation, utilisation heatmap, conflict
  impact analysis and a CP-SAT optimiser with scenario overlays.
- **Predictive risk**: Monte Carlo delivery-confidence, delay models,
  escalation engine, explainability.
- **Executive view**: the six executive questions answered in one screen,
  including a benefit-roll-up of the strategic outcomes.
- **Ask EIL**: an AI assistant with read-only tools and mandatory citations.
- **AI Inbox**: extracting execution work from meeting transcripts, email
  threads and documents (Scenario 1).
- **Integration hub**: connector registry, approved sources, sync, conflicts
  and gated write-backs.

Everything below assumes the platform is running (see §2).

---

## 2. Getting started

### 2.1 System requirements

- **Web browser**: latest Chrome, Edge, Firefox or Safari.
- **API**: nothing extra — the API is served by the backend itself.
- For the full stack (Docker/PostgreSQL/Redis/Keycloak) — see
  `infra/compose/docker-compose.yml`; on this workstation it is not available,
  so the local fallback (SQLite) is used.

### 2.2 Running the platform

| Command | What it does |
|---|---|
| `make setup` | Installs Python and Node dependencies (uv + pnpm). |
| `make migrate` | Applies database migrations to the local SQLite DB (`.data/eil.db`). |
| `make dev` | Runs the API (http://localhost:8000, Swagger `/docs`) and the web app (http://localhost:5173). |
| `make demo` | Local deterministic demo (replay mode; `AI_ENABLED=false`). |
| `make up` / `make down` | Full Docker Compose stack (requires Docker). |
| `make seed-demo` | Seeds synthetic demo data into `.data/eil.db`. |
| `make check` | CI gate: lint + typecheck + tests. |
| `make security-scan` | Secret-pattern scan + dependency audit (see §7). |

On a **fresh checkout**: `make setup && make migrate && make dev` — then open
http://localhost:5173.

Notes:

- Local mode uses SQLite + dev JWT login. In production, `AUTH_MODE=oidc` and
  users log in through the IdP (Keycloak/Entra ID).
- `make dev` boots the API with hot reload; migrations are applied at startup.
- `docs/` — capability matrix (`docs/capability-matrix.md`), executive metrics
  definitions (`docs/metrics.md`), progress tracker (`docs/PROGRESS.md`).

### 2.3 Logging in

- **Local/dev mode** (`make dev`, `make demo`): the login page
  (http://localhost:5173/login) has a role selector. Choose a role and press
  **Sign in**. On the API you can also mint tokens directly:

  ```
  POST http://localhost:8000/api/v1/auth/dev-login
  Content-Type: application/json
  {"role": "executive"}   # any role from the table in §3

  → 200 {"access_token": "eyJ...", "token_type": "bearer", "principal": {...}}
  ```

- **Production (OIDC)**: sign in with your corporate IdP; no tokens are stored
  in the browser.

API calls require `Authorization: Bearer <token>` (see §6). Health probes:
`GET /healthz`, `GET /readyz`.

---

## 3. Users, roles and permissions

### 3.1 Roles (plan §13.1)

| Role | Key capabilities |
|---|---|
| **Executive** | Dashboards, view enterprise, ask EIL, view outcomes |
| **Portfolio Manager** | Create/edit projects, manage allocations/what-if, promote scenarios, edit scoring model |
| **Project Manager** | Create/edit projects & tasks, submit demand, approve AI suggestions (own scope) |
| **Dept Head** | View enterprise, review/accept AI suggestions, promote what-if (own org) |
| **Resource Manager** | Manage allocations/what-if, promote scenarios (own org), manage resources |
| **Team Member** | View, review/accept AI suggestions (own org) |
| **PMO Analyst** | Dashboards, edit scoring model, review/accept AI suggestions |
| **AI Reviewer** | Review AI suggestions |
| **Auditor** | View audit log (read-only; cannot combine with write roles) |
| **Admin** | Everything (enterprise scope) |
| **Integration Admin** | Manage connectors & sources, approve source-registry changes |

### 3.2 Permission model

- **Deny-by-default**: every endpoint requires a permission.
- Permissions are seeded data (`docs/seed_data.py` → `role_permission`) — the
  matrix above is the seed (plan §13.1); it can be changed without code.
- **ABAC scoping**: some roles are scoped to their own organisation unit
  (e.g. `project_manager`). Enterprise-scope roles see everything.
- **SoD rules** (plan §13.2, returned as `403 sod_violation` and audited):
  - **SOD-1** — You cannot approve a demand, stage gate or change request you
    created or submitted.
  - **SOD-2** — The approver of a priority override must differ from the
    requester.
  - **SOD-3** — A user who edited the active scoring model in the current
    cycle cannot approve overrides in that cycle.
  - **SOD-4** — Changes to the Approved Source Registry or AI-processing
    flags require two distinct people (requester ≠ approver).
  - **SOD-5** — The Auditor role is read-only and must not be combined with
    any write role.
  - **SOD-6** — Scenario promotion requires approval by someone other than
    the scenario author.
- Every denial is recorded in the audit log.

---

## 4. Key concepts

### 4.1 Work items

Everything in the platform is a `WorkItem` with a type and status. Types:
`objective`, `key_result`, `demand`, `program`, `project`, `task`,
`milestone`, `commitment`, `risk`, `issue`, `benefit`, `decision`.

States: `draft`, `submitted`, `approved`, `rejected`, `active`, `on_hold`,
`completed`, `cancelled`.

### 4.2 The work graph (Enterprise Work Graph, Phase 2)

Work items are linked with typed edges. Rules are data-driven
(`link_type_rule`, plan §7.2):

- `part_of` — item is part of another item.
- `aligns_to` — objective/key-result alignment.
- `fulfils` — commitment ← project/program.
- `realizes` — benefit → objective/project/program.
- `mitigates` — risk/issue ← task/project/program/objective.
- `depends_on` — dependency edges (cycle-rejected on `depends_on`).
- `duplicate_of` — duplicate detection links.

Graph operations: neighbours, lineage, path, downstream-impact
(`GET /graph/nodes/{id}/downstream-impact`), plus an integrity report
(`GET /graph/integrity`: cycle detection, orphans, duplicate edges).

### 4.3 Strategic outcomes

- **Objectives** (OKRs): top of the hierarchy — see **Strategic outcomes**
  (§5.2).
- **Key results**: OKRs under objectives.
- **Demands**: business requests; approve → **auto-converted** into a
  program/project from a delivery template (WBS, milestones, gates, benefits),
  carrying alignment links and scores (`POST /prioritization/{item_id}/override`
  flow; `eil/modules/prioritization/conversion.py`).
- **Benefits**: strategic outcomes realised by objectives (roll-up in §5.11).
- **Commitments**: delivery promises with due dates and delivery confidence
  (Monte Carlo, §5.9).

### 4.4 Allocation & capacity (Scenario 3)

- **Allocations**: planned hours per resource per date window. Create on the
  Capacity page (form: resource, optional work item, start/end, hours per
  week). Backend: `GET/POST /allocations`, `PATCH /allocations/{id}`
  (admin role).
- **Heatmap**: per-resource weekly utilisation — green/amber/red by
  `capacity_amber_pct` (85) / `capacity_red_pct` (100).
- **Conflicts**: overloads with impacted commitments/projects/objectives
  (graph downstream-impact with criticality weighting).

### 4.5 Synchronisation (systems of record)

- **Approved sources** (admin): register external systems (`type` ∈ p6, eam,
  erp, hr, m365).
- **Sync now**: `POST /integrations/sources/{id}/sync` — runs a pull
  immediately; beat polls every 60 s when no Redis.
- **Health + lag**: `GET /integrations/sources/{id}/status` — health status,
  last sync time, lag, error count, unresolved conflicts.
- **Conflicts**: external changes to non-owned fields — list
  (`GET /integrations/sources/{id}/conflicts`), resolve
  (`POST .../conflicts/{id}/resolve`).
- **Write-backs**: gated, approval-based reference writes to systems of record
  (approve/execute; default off).
- **AI processing flags**: gated by SOD-4.

---

## 5. Feature walkthrough

### 5.1 Dashboard (Execution overview) — `/` (all roles)

Commitments total, average delivery confidence by org unit, RAG status,
overdue and upcoming items, pending approvals, at-risk items.

### 5.2 Objectives & OKRs — `/objectives`

List and edit objectives and key results. Open an objective to see:
- its key results,
- its demand children (with alignment),
- downstream impact (graph),
- benefit roll-up (see §5.11).

Create via the page's create form.

### 5.3 Demand pipeline — `/demand`

List of demands; submit a new demand (title, description, priority, demand→
objective alignment); approvers receive it on the **Approvals** page.

### 5.4 Approvals — `/approvals`

Inbox of items awaiting your decision: approve, reject (with reason),
or delegate/escalate per governance workflows. Approvals are time-boxed
(`approval.due_at`) and can be escalated.

### 5.5 Audit log — `/audit`

Hash-chained, append-only audit log of every privileged action (see §4.5 of
plan §13.2/§13.1). Export and filter available in the UI; tampering is detected
by hash chains on export (`nelson`-style verification via the audit service;
see `eil/modules/audit/service.py`).

### 5.6 Work graph — `/graph` (all roles)

A React Flow canvas:
- Pick a root item ("Select a root item").
- **Neighbours**, **Lineage** (part_of/aligns_to chains), **Downstream impact**
  (affected items with criticality).
- Filters by link type; colour by RAG/confidence; expand/collapse.

### 5.7 Prioritisation board — `/prioritization` (portfolio_manager, admin)

- Each item: rank, type, tier (1–4), score, rationale, cut-line badge.
- **Score**: `score = 100 × Σ wᵢ·nᵢ` over anchored criterion scales; tier
  thresholds per plan §9.1; gate rules (HSE/regulatory).
- **Override form**: raise the tier with justification + a distinct approver —
  submitting as yourself is rejected with `403 sod_violation` (SoD-2); every
  override is audited (`priority.overridden`).
- Approve the demand at `/demand` → the project is auto-created from the
  delivery template with alignment links and scores.

### 5.8 Capacity & what-if — `/capacity` (resource_manager, portfolio_manager, admin)

- **Heatmap**: resource × week utilisation with tooltips (demand, available,
  utilisation).
- **Allocations** (new): create allocations with the form on this page; list
  and edit hours-per-week per allocation.
- **Conflicts**: impact cascade — affected commitments/projects/objectives per
  overload, with criticality.
- **Optimiser**: four strategies (reassign / resequence / reprioritise /
  augment) with quantified deltas (unmet/overload hours, etc.).
- **Scenarios / what-if**: create scenarios, tweak allocations, view metrics
  deltas against the baseline, promote through approval (SoD-6).

### 5.9 Risk & escalations — `/risk` (all roles)

- **Risk radar**: at-risk items with confidence × impact, coloured by risk
  score; sorted by risk score.
- **Escalation inbox**: open escalations with due dates; acknowledge
  (`PATCH /api/v1/escalations/{id}/acknowledge`).

### 5.10 Executive view — `/executive` (executive)

Six panels:
1. **Committed to what** — commitments by org unit, min/avg confidence.
2. **Most important** — top priorities with scores and override flags.
3. **Where constrained** — capacity constraint (resource, week, status).
4. **What's at risk and why** — risk radar + drivers.
5. **Strategic outcomes affected** — objectives with confidence + benefit
   counts (roll-up, see §5.11).
6. **Where intervention required** — open escalations + recommended decisions.

### 5.11 Benefits / strategic outcome roll-up — `GET /api/v1/items/benefit-rollup`

Per active objective: benefit count, key-result count, total actual/target/
forecast, latest actual date, on-track flag. Rendered as the
**"Strategic outcomes — benefit roll-up"** panel on the Executive page.

### 5.12 Presenter mode — `/executive/presenter`

Full-screen executive view:
- **As-of selector** — scrub the timeline to replay the view as of any past
  date (replay semantics).
- **Auto-refresh** toggle.

### 5.13 Ask EIL — `/assistant` (all roles with `ai.assistant`)

Type a question; EIL answers using read-only tools
(`query_graph`, `get_capacity`, `list_commitments`, `get_risks`,
`explain_confidence`, `get_priorities`) and cites entity IDs from the results.
When AI is disabled (local mode: `AI_ENABLED=false`), the page shows the
graceful "unavailable" state and the API returns `409 not_available`.
Conversation history: `GET /api/v1/assistant/conversations` (T8.3).

### 5.14 AI Inbox — `/ai/inbox` (review/accept roles)

Review AI suggestions from meeting/email extraction:
- **Accept** — promote to a task/commitment with `derived_from` provenance
  (evidence quote, speaker, timestamp, model, prompt version, reviewer).
- **Edit-and-accept** — edit the payload, then accept.
- **Reject** with a reason (stored as feedback; drives weekly metrics).
- **Bulk reject** selected suggestions.
- **Duplicate panel** — link duplicates to existing items (`duplicate_of`).

### 5.15 Administration — Connectors — `/admin/connectors` (integration_admin, admin)

- **Connectors table**: system, record types, modes, push support.
- **Sources**: create (`type`, `name`, `owner` required — SOD-4 for
  protected changes), enable/disable, **delete when disabled**, **Sync now**
  (`POST /integrations/sources/{id}/sync`), **AI processing** (SOD-4
  two-person rule — needs a second approver when enabling).
- **Conflicts**: external changes to non-owned fields — resolve.
- **Write-backs**: approve/execute gated writes.

---

## 6. API appendix (main endpoints)

All calls: `Authorization: Bearer <token>`; API prefix `/api/v1`.

| Area | Endpoints (role) |
|---|---|
| Health | `GET /healthz`, `GET /readyz` |
| Auth | `POST /auth/dev-login` |
| Dashboard | `GET /dashboard`, `GET /metrics/summary` |
| Executive | `GET /executive/brief` (executive) |
| Prioritisation | `GET /prioritization`, `POST /prioritization/{id}/override` |
| Allocations | `GET /allocations`, `POST /allocations`, `PATCH /allocations/{id}` |
| Capacity | `GET /capacity/heatmap`, `GET /capacity/conflicts`, `POST /capacity/optimise`, `GET/POST/PATCH /scenarios…` |
| Benefits | `GET /items/benefit-rollup` |
| Graph | `GET /graph/nodes/{id}/neighbors`, `.../lineage`, `.../downstream-impact`, `GET /graph/path?from=&to=`, `GET /graph/integrity` |
| Risk | `GET /risk/radar`, `GET /escalations`, `PATCH /escalations/{id}/acknowledge` |
| Assistant | `POST /assistant/ask`, `GET /assistant/conversations` |
| Items | `GET /items…`, work links, benefit measurements/realisation |
| Integrations | `GET/POST/PATCH/DELETE /integrations/sources`, `POST .../sync`, `GET .../status`, `GET .../conflicts`, `POST .../resolve`, write-backs |
| Audit | `GET /audit…` (view; `make security-scan` for scans) |

Capability matrix (delivery status per capability): `docs/capability-matrix.md`.

---

## 7. Troubleshooting

### 7.1 403 Forbidden — why

The endpoint requires a permission your role doesn't have (deny-by-default).
Examples:
- `GET/POST /integrations/sources` → `connector.manage` — held by
  **integration_admin** and **admin** only. Log in as one of those roles:

  ```
  POST /api/v1/auth/dev-login  {"role": "integration_admin"}
  ```

- `GET /api/v1/prioritization` requires `work.view`; Scenario 2 override needs
  `PRIORITY_OVERRIDE` (portfolio_manager/admin).

### 7.2 422 Unprocessable Entity on creating a source

`POST /integrations/sources` validates `type`, `name` and `owner` — fill
**name** and **owner** in the form (the Create button now disables until
both are set). `type` must be one of the built-in connector systems
(p6, eam, erp, hr, m365).

### 7.3 Alembic-managed databases — migration drift (fixed)

Older databases had a drift between models and migrations (the `Score`
table was missing timestamp columns). Fixed by migrations
`0008_add_missing_timestamp_columns` + `0009_drop_score_version`; a
regression test (`apps/api/tests/test_migration_drift.py`) runs
`alembic upgrade head` on a scratch DB and diffs against the models.

### 7.4 Browser e2e and live AI

- Playwright browser tests are **not executed in this environment** (no
  browser binaries available); they run in CI.
- Live AI requires `GROQ_API_KEY` and `AI_ENABLED=true`; the local demo uses
  replay mode (`LLM_MODE=replay`).
- The Keycloak/OIDC browser flow cannot be verified without Docker/Keycloak;
  realm/users/groups/MFA are authored and validated in the compose stack.

### 7.5 Security notes

- CSP header + security headers on all API responses (Phase 9, T9.2).
- Per-principal/IP rate limiting (Phase 9, T9.2).
- CORS allow-list + `TrustedHostMiddleware` — outside local/ci/demo,
  `CORS_ORIGINS` and `TRUSTED_HOSTS` must be set (Settings fails closed).
- SSRF guard for connector URLs (`connectors/sdk/urls.py`).
- `make security-scan`: secret-pattern scan + `pip-audit` dependency audit —
  wired into CI.
- ASVS L2 checklist: `docs/asvs-l2-checklist.md`.

---

## 8. Glossary

- **SoD (SOD-1..6)** — segregation of duties rules; denials are audited.
- **SOD-4** — two-person rule for source-registry/AI-flag changes.
- **Benefits** — measurable realised outcomes of objectives (realises links).
- **Allocation** — planned hours per resource per date window.
- **What-if** — scenario overlays of allocations/priorities; promote to
  baseline through approval.
- **Conflict** — external change to a non-owned field (resolve = keep local).
- **Dual-check on override** — two distinct approvers; original tier preserved
  (`original_tier` on the override).
- **SIM badge** — items originating from a simulated (demo) system.
- **Replay mode** — deterministic LLM replay used by the local demo (no
  `GROQ_API_KEY` needed).

---

## 9. Getting more help

- `docs/PROGRESS.md` — implementation progress tracker (todo/doing/done).
- `docs/capability-matrix.md` — delivery status per capability.
- `docs/metrics.md` — executive metrics definitions.
- `docs/runbooks/` — demo scenario runbooks (1–5).
- `seed/scenarios/` — seeded starting states per scenario.
- Git history (`git log --oneline`), ADRs in `docs/adr/`.
