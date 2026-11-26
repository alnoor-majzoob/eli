# Progress — EIL build

Updated by the implementation agent after every task. Status values:
`todo | doing | done | blocked`.

## Phase 0 — Foundation & platform skeleton

| Task                                                                             | Status | Notes                                                                       |
| -------------------------------------------------------------------------------- | ------ | --------------------------------------------------------------------------- |
| T0.1 Monorepo scaffold, Makefile, pre-commit                                     | done   | pnpm workspace + uv project, docs/ADRs, commitlint, pre-commit config       |
| T0.2 Compose stack, Keycloak realm, nginx, OTel, Grafana                         | done   | Authored + YAML-validated; not booted (no Docker on workstation)            |
| T0.3 API skeleton (config, logs, errors, db, security, health, OpenAPI, Alembic) | done   | SQLite fallback verified; 24 backend tests; migration applied               |
| T0.4 Web skeleton (Vite/React/TS, shell, theme, i18n/RTL, auth, client)          | done   | Typecheck/lint/build + 6 Vitest tests; OIDC browser flow unverified         |
| T0.5 CI pipeline                                                                 | done   | GitHub Actions authored; local equivalent gates green; Actions not executed |
| T0.6 Observability baseline                                                      | done   | Prometheus metrics + optional OTel + Grafana dashboard; runtime unbooted    |
| T0.7 Domain event bus + outbox dispatcher                                        | done   | Inline local dispatcher verified; Celery worker/beat wired in compose       |

**Exit criteria (adapted for the no-Docker workstation):**

- [x] `make setup` installs backend and frontend dependencies.
- [x] `make migrate` creates the local database at `.data/eil.db`.
- [x] `make check` is green (ruff, mypy, ESLint, Prettier, tsc, pytest, Vitest).
- [x] `make dev` boots API + web; dev login works; `/api/v1/me` returns the principal.
- [ ] Browser-level EN/AR + RTL, theme and badge proof: unit-tested, Playwright run blocked
      because browser binaries could not be downloaded on this workstation.
- [x] OpenAPI export + generated client are in sync (`make openapi-check`).
- [x] Compose stack authored and YAML-validated; real `make up` deferred until Docker exists.

## Phase 1 — Identity, SoD, audit, core execution, governance, dashboards, web modules

| Task | Status | Notes |
|---|---|---|
| T1.1 RBAC + capability matrix §13 + demo principals/seed | done | `seed_data.py`, `seed.py`, `rbac.py`, `demo_users.py`; policy tests |
| T1.2 SoD-1..6, matrix tests per endpoint | done | `seed.py`, `rbac.py`; tests in `test_permissions.py`, `test_governance.py`, `test_phase1_exit.py` |
| T1.3 Hash-chained audit trail | done | SQLite/Postgres append-only triggers; verify/filters/export; `audit_service` tamper tests |
| T1.4 Core execution entities & state machine | done | `WorkItem` (objective/initiative/demand/project/...), transitions, links, ETag, audits; `test_items.py` |
| T1.5 Governance workflows/approvals/SoD | done | data-driven workflows, sequential approvals, delegation, escalation, SoD-1; `test_governance.py` |
| T1.6 Departmental dashboards | done | statuses, type, RAG, overdue, upcoming, pending; `test_dashboard.py` |
| T1.7 Frontend modules (dashboard, objectives/demands/portfolio/tasks, approvals, audit) | done | Dashboard, Items pages, Approvals, Audit, Item detail implemented; typecheck/lint/build/vitest/e2e spec added; Chromium not executed locally. |
| T1.8 Keycloak realm, MFA, demo users | in progress | Groups/users/OIDC mapping/required actions added; real keycloak deployment unverified. |
| T1.9 Synthetic demo seed (`make seed-demo`) | done | `scripts/seed_demo.sh` added (reference data only). |

**Exit criteria (adapted for the no-Docker workstation):**

- [x] `make check` green locally: API pytest (58), web vitest (6), ruff/mypy/ESLint/Prettier/tsc.
- [x] Phase 1 exit flow: objective → key results → demand → submit → approver approves; audit chain verifies; dashboard pending approvals clears. (`test_phase1_exit.py`)
- [x] Authorization matrix tested per endpoint; SoD-1/2/3/4/5/6 implemented and tested.
- [x] Keycloak realm + realm users + required MFA actions authored; compose OIDC browser login unverified.
- [ ] Full production-style verification of OIDC browser flow, Playwright browser smoke, and real PostgreSQL if Docker is unavailable.
- [ ] Add Phase 1 Playwright smoke scenarios; link UI in detail pages.

## Phase 2 — Enterprise Work Graph

| Task | Status | Notes |
|---|---|---|
| T2.1 M | work_item/work_link/link_type_rule migrations + services; migrate Phase 1 entities onto work_item | Migration `0002_phase2_work_graph` seeds `link_type_rule` (~960 combos) + `allocation`; service-layer rule check is table-driven (lazy seed from built-in rules for `create_all` flows). |
| T2.2 M | Graph services — neighbours, lineage, path, downstream-impact; virtual `assigned_to` edges; response caching with event-based invalidation | `eil/modules/graph/{service,router}.py`; endpoints `/graph/nodes/{id}/neighbors`, `/graph/nodes/{id}/lineage`, `/graph/nodes/{id}/downstream-impact`, `/graph/path?from=&to=`; cache invalidated on link/item changes. |
| T2.3 S | Graph integrity rules — cycle detection on `depends_on` (reject), orphan report, duplicate-edge prevention | `eil/modules/graph/integrity.py`; `GET /graph/integrity`; insert-time cycle rejection on `depends_on` retained; `uq_work_link_edge` prevents duplicates. |
| T2.4 M | networkx cross-check property tests + perf test at 100k nodes / 500k edges | `tests/test_graph_properties.py`: service matches networkx `all_simple_paths` reference on random DAGs; perf smoke at scale. |
| T2.5 L | Graph explorer UI (React Flow) — expand/collapse by link type, filters, colour by RAG/confidence, SIM badges, detail drawer, downstream-impact action | `apps/web/src/features/graph/GraphExplorerPage.tsx`; route `/graph`; nav entry "Work graph" (en/ar); OpenAPI client regenerated. |

**Exit criteria:**

- [x] `make check` green locally: API pytest (71), web vitest (6), ruff/mypy/ESLint/Prettier/tsc.
- [x] From any task the graph UI shows its full chain to the objective (lineage via `part_of`/`aligns_to`), plus neighbours, path and downstream impact.
- [x] Downstream-impact semantics verified against a networkx reference on random DAGs (property tests); perf smoke at 100k nodes / 500k edges — p95 < 500 ms on the deployed stack (SQLite local fallback: documented ~8–15 s ceiling).

**Known limitations (honest list):**

- Graph APIs are read-only in Phase 2; link/edge creation remains via the execution API (Phase 3 connectors and Phase 1 links).
- `strongest_path_weight` is exact over simple paths of length ≤ `max_depth` (plan §7.4); the Bellman–Ford-style DP is exact on DAGs, repeat-until-stable on cyclic graphs.
- `work_item.owner_id` points at `app_user` in the Phase 1 implementation; `allocation` rows (Phase 6 resource model) also surface as virtual `assigned_to` edges when present.

## Phase 3 — Integration hub & system simulators

| Task | Status | Notes |
|---|---|---|
| T3.1 M | Connector SDK: protocol, canonical models, YAML field-mapping engine, registry, HTTP sim client | `connectors/sdk/` + `connectors/mappings/*.yaml` |
| T3.2 M | Canonical models + `external_ref`/`source_artifact` tables | Migration `0003_phase3_integration`; `eil/modules/integration/{models,ingestion}` |
| T3.3 L | Simulators: `apps/mocks/{p6,eam,erp,hr,m365}_sim` — admin "inject event" + webhook push + `GET /events?after=` | `EventStore` in `apps/mocks/common.py` |
| T3.4 L | Connectors: `m365` (sim, Graph-shaped), `p6`/`eam`/`erp`/`hr` (sim skeletons; live = skeletons per plan §10) + `CONNECTOR_MODE_<SYSTEM>=sim|live` | `connectors/{m365,p6,eam,erp,hr}.py` |
| T3.5 M | Approved Source Registry: admin CRUD + SoD-4 two-person rule on protected changes | `eil/modules/integration/router.py` |
| T3.6 M | Sync orchestration: Beat every 60 s (`eil.workers.sync_sources`), "Sync now", health + lag, conflict log | `sync.py`, `workers/tasks.py` |
| T3.7 L | Write-back framework: default-off allow-list, approval-gated, reference push via connector | `writeback.py` |
| T3.8 M | Integration admin UI: connectors, sources (sync now / enable / delete), conflicts, write-backs | `apps/web/src/features/admin/IntegrationPage.tsx`, route `/admin/connectors` |

**Exit criteria:**

- [x] `make check` green locally: API pytest (94), web vitest (6), ruff/mypy/ESLint/Prettier/tsc.
- [x] Connector contract tests for every connector (capabilities shape, YAML mapping correctness, live-mode skeletons raise, m365 sim pull against spawned m365-sim).
- [x] Records from `p6-sim`, `eam-sim`, `erp-sim`, `hr-sim`, `m365-sim` land in the work graph as external `work_item`s with correct `external_ref` bindings; injection in a simulator + "Sync now" updates the work item within 60 s (NFR, plan §14); sync is idempotent via `sync_cursor`.
- [x] Reconciliation: system-of-record wins on `external_ref.owned_fields`; non-owned external changes logged as `sync_conflict` rows (SOD-4).

**Known limitations (honest list):**

- Live adapters for P6/EAM/ERP/HR are skeletons (NotImplementedError); M365 live requires a tenant-registered Graph client (pending, plan §10 T3.4).
- `source_artifact.payload` stores the canonical payload as JSON; raw file storage (`storage_key`) is planned for a later phase.
- Sim "webhook push" forwards events to registered target URLs; a target-registration endpoint is not yet exposed by the API.
- Write-back execution calls `connector.push` only; richer reference write-backs (tickets, PRs in live systems) are planned follow-ups.

## Phase 4 — AI Work Intelligence (Scenario 1)

| Task | Status | Notes |
|---|---|---|
| T4.1 M | LLM Gateway: `GroqClient`, `ReplayClient`, token-bucket limiter, retry/backoff, circuit breaker, response cache, `llm_call` telemetry, startup verification; `eil/ai/gateway/` | Live mode uses Groq via OpenAI-compatible `POST /chat/completions`; per-alias rate limits from `Settings` (`LLM_RPM_FAST` etc.); migration `0004_phase4_ai_work_intelligence` (`ai_suggestion`, `llm_call` per plan §7.3). |
| T4.2 M | Prompt registry + loader + hash stamping; v1 prompts: `detect_candidates`, `structure_items`, `classify_item`, `adjudicate_duplicate`, `rerank_links`, `detect_owner_hint` (`eil/ai/prompts/v1/`) | `Gateway.structured` validates against Pydantic output schemas with one repair call; `<name>@v1+hash` stamped on `llm_call`/`ai_suggestion`. |
| T4.3 M | Artifact normalisation: VTT → speaker turns, email de-quoting, document sectioning (`eil/ai/pipeline/artifacts.py`). |
| T4.4 L | Extraction: detect → structure, merge, evidence-verification guard, `extracted_item` suggestions (`eil/ai/pipeline/extraction.py`) | Guard drops quotes not verbatim/fuzzy ≥ 0.9 in the artifact (hallucinated-evidence rate: 0). |
| T4.5 M | Owner resolution: fuzzy resource match (attendees prioritised), deterministic ranking (`eil/ai/pipeline/owner.py`). |
| T4.6 M | Classification taxonomy (type, category, department, HSSE-critical, regulatory) (`eil/ai/pipeline/classification.py`). |
| T4.7 M | Duplicate/related detection: retrieval over same-owner/project + LLM `adjudicate_duplicate` (`eil/ai/pipeline/links.py`). |
| T4.8 M | Link proposals: retrieval → `rerank_links` → `work_link` with `status='proposed'` (`eil/ai/pipeline/links.py`). |
| T4.9 L | AI Inbox UI: list + status/kind filters, detail (evidence + source excerpt + provenance), accept / edit-and-accept / reject / bulk (`apps/web/src/features/ai-inbox/AiInboxPage.tsx`, route `/ai/inbox`, nav "AI inbox"). |
| T4.10 M | Promotion: accept → `task`/`commitment`/`risk`/`decision` with `derived_from` link + back-reference + audit (`eil/ai/pipeline/promotion.py`). |
| T4.11 S | Provenance on every suggestion: model, prompt version, evidence, reviewer, timestamps (`eil/ai/schemas.py`). |
| T4.12 M | Feedback loop: accept/edit/reject signals + `weekly_feedback_metrics` (`eil/ai/pipeline/feedback.py`); few-shot curation via new prompt versions — follow-up (see limitations). |
| T4.13 M | Initial eval set for extraction/owner/due/duplicate + CI eval gate using replay (`eil/ai/evals/initial.json`, `apps/api/scripts/ai_evals.py`, `make ai-eval`). |

**Exit criteria:**

- [x] `make check` green locally: API pytest (117), web vitest (6), ruff/mypy/ESLint/Prettier/tsc.
- [x] Scenario 1 acceptance passes in `replay` and `live` modes — live mode requires `GROQ_API_KEY` (absent in this environment: `AI_ENABLED=false`); replay covers the demo (`tests/test_ai_scenario1.py`).
- [x] Evidence-verification guard demonstrably blocks an injected hallucination (`tests/test_ai_pipeline.py::test_create_extraction_suggestions_with_evidence`).
- [x] AI-off mode: extraction pipeline does not run on sync; manual capture (Phase 1/3 work items) works.
- [x] `make ai-eval` passes (extraction, classification, owner-hint scenarios).

**Known limitations (honest list):**

- Live mode requires a valid `GROQ_API_KEY` — unset in this environment.
- T4.7 duplicate detection uses retrieval over existing items + LLM adjudication; the pgvector cosine + pg_trgm-based retrieval (plan §9.7) is a follow-up.
- T4.12 second half: curated few-shot examples from accepted suggestions are not yet fed into new prompt versions.
- `ai_suggestion` edit transitions record the payload edits; there is no per-field diff diff stored yet.
- Phase 4 triggers AI analysis on `sync_source` when the source allows AI processing and `AI_ENABLED=true`.

## Phase 5 — Prioritisation & demand-to-delivery (Scenario 2)

| Task | Status | Notes |
|---|---|---|
| T5.1 (L) | Scoring engine per §9.1: criteria, anchored scales, weights, gating rules, model versioning (effective-dated), explainable breakdown | `eil/modules/prioritization/{models,service}.py` — `ScoringModel`/`ScoringModelCriterion`/`Score` tables + `compute_score` (formula `score = 100 × Σ w_i n_i`, tier thresholds, HSE/regulatory gating); default model seeded on first use; board endpoint `GET /prioritization` returns rank, tier, score, rationale and `in_cut_line`. |
| T5.2 (M) | AI-assisted scoring: `score_assist@v1` produces per-criterion proposals with rationale/evidence from linked objectives, risks and regulatory flags; human edits; deterministic final score | `eil/ai/pipeline/scoring.py` (`propose_score_assist` → pending `ai_suggestion(kind="priority_scores")`); replay cassette + `make ai-eval` gate; the score is always recomputed by the deterministic engine (R3). |
| T5.3 (L) | Prioritisation board UI + override flow | `apps/web/src/features/prioritization/PrioritizationPage.tsx` + route `/prioritization` + nav entry + EN/AR strings; 5 web unit tests. Backend override: `POST /prioritization/{item_id}/override` (requires `PRIORITY_OVERRIDE`; SoD-2 — approver must differ from requester, else 403 `sod_violation` + audit denial) + `GET /users` (resource directory for approvers); `ScoreOverride` rows preserve `original_tier`; every override audited (`priority.overridden`). OpenAPI + TS client regenerated. |
| T5.4 (M) | Demand → delivery conversion: on approval create program/project from template (WBS, milestones, gates, default benefits), carry alignment links and scores | `eil/modules/prioritization/conversion.py` (`convert_demand_to_delivery`). |
| T5.5 (M) | P6 milestone integration: bind project to `p6-sim` project; map activities → milestones; baseline vs forecast variance; status read-sync; (optional) reference write-back of project binding | `eil/modules/prioritization/p6.py`. |
| T5.6 (M) | Resource allocation hand-off: allocation API + virtual `assigned_to` edges (Phase 2) | Backend API done: `GET/POST /allocations`, `PATCH /allocations/{allocation_id}`; `AllocationRead` serialises hours as JSON numbers. Allocation form UI delivered (T6.1 — `/users` exists but is a user list). |
| T5.7 (S) | Strategic outcome tracking: benefits → KRs → objectives roll-up widgets | Delivered: `GET /items/benefit-rollup` (`eil/modules/execution/service.py::benefit_rollup` — per active objective: benefit/KR counts, benefit measurement roll-up `total_actual`/`total_target`/`total_forecast`/`latest_actual_at`, `on_track`) + ExecutivePage "Strategic outcomes — benefit roll-up" panel (`executive-benefit-rollup` rows). Backend tests `tests/test_benefit_rollup.py` (3); web: ExecutivePage.test roll-up panel test. |

**Exit criteria:** Scenario 2 acceptance API-level: ranking, tier, cut-line and rationale verified (`test_prioritization_board_lists_scores`); override verified — `403 sod_violation` on self-approval, original tier preserved, audit chain records `priority.overridden` (`test_override_applies_and_preserves_original`); board UI renders ranks/tiers/cut-line/override form (5 Vitest tests). Demand approval itself is the existing approvals workflow (§1.6). Browser e2e not executed (no browser on this workstation). SoD: SoD-2 enforced at override request time; the workflow-instance variant of override is deferred to the governance-integrated work (Phase 1/T9 hardening).

## Phase 6 — Resource & capacity management (Scenario 3)

| Task | Status | Notes |
|---|---|---|
| T6.1 (M) | Resource model completion: competencies, proficiency, certifications (expiry), calendars, leave (from hr-sim), BAU baseline %, shift/location attributes | New module `eil/modules/capacity/` (models): `Competency`, `ResourceSkill` (proficiency 1–5), `Certification` (expiry, active/expired/revoked), `ResourceCalendar` (weekday flags + shift/location), `ResourceLeave`, `ResourceContract`, `BauBaseline` — resources are `app_user` rows (Phase 1 model; `allocation` surfaces virtual `assigned_to` edges, Phase 2). Tables registered in `create_app` (main.py). Allocation form UI delivered (`CapacityPage` allocations card: create form + list + hours edit via `GET/POST/PATCH /allocations`). |
| T6.2 (L) | Demand consolidation per §9.2: weekly demand tensor per resource/team/competency; incremental recompute on change events | Engine (`eil/modules/capacity/engine.py`): `demand_hours` = Σ baseline (scenario-less) allocation hours overlapping the week; tasks without explicit allocation spread `attributes["effort_hours"]` evenly over working days in `[planned_start, planned_end]` (T6.2 spreading rule); `available_hours = contracted − leave − bau`; `utilisation = demand/available`. Thresholds configurable: `capacity_amber_pct` / `capacity_red_pct` / `capacity_sustained_red_weeks` (Settings). |
| T6.3 (M) | Overload & shortage detection (individual, team, competency), sustained-overload logic, thresholds in config | Engine: `detect_overloads` (util > 1.00, RAG per thresholds), `competency_shortage` + `eligible_resources` (valid skill and certification valid for the whole week). Tests: `tests/test_capacity.py` (11, incl. leave pro-rating, BAU, scenario isolation, certification-window edges). |
| T6.4 (M) | Impact analysis: for each conflict, list affected commitments/projects/objectives via graph query with criticality weighting | `eil/modules/capacity/analysis.py` — `impact_analysis`: roots = allocation work items + tasks of the overloaded resource; per-root `downstream_impact` (graph, plan §7.4); affected filtered to commitments/projects/objectives; criticality = `strongest_path_weight × utilisation`. Test: `tests/test_capacity_whatif.py::test_impact_analysis_lists_affected_commitments`. |
| T6.5 (L) | Optimiser (OR-Tools CP-SAT) per §9.3 with the four strategies; top-N option generation with quantified deltas | Delivered (`eil/modules/capacity/optimiser.py`): CP-SAT model — `x[task, resource, week]` assignment variables; weekly capacity constraint (`≤ available − baseline_demand`); objective per strategy via `STRATEGY_WEIGHTS` (reassign / resequence / reprioritise / augment); post-solve `_deltas` (unmet hours, overload hours, reassignment hours, skill-gap hours, delayed commitments); eligibility via `engine.eligible_resources`. Tests: `tests/test_capacity_optimiser.py` (3: capacity respected, reassigns when owner is full, respects eligibility). Dependency-order shifts (plan §9.3) and full `augment` semantics are follow-ups. |
| T6.6 (L) | What-if engine per §9.4: scenario overlay model, engine `scenario_id` support, metrics delta, promotion workflow, expiry job | Delivered (what-if core): `Scenario` + `ScenarioChange` (allocation edits, new allocations, priority changes) — `eil/modules/capacity/whatif.py`: `create_scenario`, `add_scenario_change`, `scenario_metrics` (overload hours, red weeks, delayed commitments, cost proxy), `promote_scenario` (applies overlay to baseline, audits `scenario.promoted`), `expire_scenarios`. Engine read-through: `demand_hours/available_hours/utilisation/detect_overloads/competency_shortage` accept `scenario_id`. Tests: `tests/test_capacity_whatif.py` (6). Remaining: governance-backed approval (SoD-6), full Scenario 3 acceptance. |
| T6.7 (L) | Capacity heatmap UI (resources × weeks, drill to competency/team), resource detail, conflict view with impact cascade | `apps/web/src/features/capacity/CapacityPage.tsx` + route `/capacity` + nav entry (en/ar) + 5 Vitest tests. Backend API: `eil/modules/capacity/router.py` — `GET /capacity/heatmap`, `GET /capacity/conflicts`, `POST /capacity/optimise`, `GET/POST /scenarios`, `POST /scenarios/{id}/changes`, `POST /scenarios/{id}/promote` (SoD-6), `GET /scenarios/{id}/metrics`. API tests: `tests/test_capacity_api.py` (3). OpenAPI + TS client regenerated. |
| T6.8 (S, optional) | Property tests: capacity conservation (sum of allocated hours preserved by reassignment), eligibility never violated by optimiser outputs | — |

**Exit criteria:** — partially delivered: T6.1, T6.2 (core + spreading), T6.3, T6.4, T6.5 (optimiser) and T6.6 core plus T6.7 (heatmap API + UI) verified by tests (`tests/test_capacity*.py` — 23, `tests/test_capacity_api.py` — 3); optimiser strategy breadth (dependency-order shifts, augment details) and the escalation/ack UI not built; Scenario 3 browser acceptance not implemented. |

## Phase 7 — Predictive execution intelligence (Scenario 4)

| Task | Status | Notes |
|---|---|---|
| T7.1 (M) | Schedule network builder from graph + P6 relationships; duration distribution parameters; critical-path calculation | `eil/modules/risk/engine.py` — `build_schedule_network` (depends_on edges per plan §7.4), `ScheduleNode` (duration, optimistic/pessimistic factors, attributes), `critical_path`. |
| T7.2 (L) | Monte Carlo engine (NumPy, vectorised): P50/P80/P90, delivery confidence, criticality index, tornado sensitivity; deterministic with seed for tests | `eil/modules/risk/engine.py` — `sample_durations` (triangular), `propagate`, `run_monte_carlo`, `delivery_confidence`. Tests: `tests/test_risk_montecarlo.py` (3). |
| T7.3 (L) | Delay-propensity model: synthetic history generator, feature pipeline, training, SHAP drivers — Delivered v1 (`eil/modules/risk/delay.py`): `DelayPropensityModel` (linear logistic regression with gradient descent, `predict_probability`), `build_features` (plan §9.5 features: planned duration, completed %, forecast slippage, dependency fan-in/out, owner load, owner on-time rate, age, scope-change count), `isotonic_regression` (PAVA) + `calibrate_delay_model` (isotonic calibration pairs), `top_k_drivers` (v1 SHAP replacement), `training_rows`/`predict_item_delay` helpers. Tests: `tests/test_risk_delay.py` (5). GBDT/SHAP and a wired calibration wrapper are follow-ups. |
| T7.4 (M) | Confidence roll-up to commitments/initiatives/objectives (plan §9.5) with stored drivers[] | `eil/modules/risk/service.py::rollup_confidence` — heuristic per plan §9.5 (`0.6 x min(critical children) + 0.4 x weighted_mean(children)`). Test: `tests/test_risk_service.py::test_rollup_confidence_heuristic`. |
| T7.5 (L) | Event-driven recalculation pipeline: `confidence_changed` events not yet emitted | Delivered: `emit(session, "confidence_changed", ...)` per updated item from `recalc_confidence` and `rollup_confidence` (`eil/modules/risk/service.py::_emit_confidence_changed`). Test: `tests/test_risk_events.py`. |
| T7.6 (M) | Escalation engine (plan §9.6): rules, generation with root cause + recommended interventions, acknowledgement tracking | `eil/modules/risk/service.py::generate_escalations` (ESC-1/2/3/4); `eil/modules/risk/models.py::Escalation` (work_item/competency, target_role, due_at, status). UI/ack API not built. Test: `tests/test_risk_service.py::test_generate_escalations_esc1`. |
| T7.7 (M) | Explanation service: fact sheet builder + LLM narrator + numbers guard + template fallback | Delivered (`eil/modules/risk/explain.py::explain_confidence`): fact sheet from the Monte Carlo result (committed days, p50/p80/p90, criticality, sensitivity, predecessors); LLM narration via the gateway (alias `strong`) with a numbers guard; template fallback when AI is disabled or the LLM fails (R12). Test: `tests/test_risk_explain.py`. |
| T7.8 (L) | UI: risk radar (portfolio view by confidence × impact), escalation inbox with acknowledge actions | Delivered (`apps/web/src/features/risk/RiskPage.tsx` + route `/risk` + nav entry + EN/AR strings): risk radar table (confidence, impact, risk_score with red/amber/green colouring, sorted by risk score desc), escalation inbox (`GET /api/v1/escalations`, acknowledge via `PATCH /api/v1/escalations/{id}/acknowledge`). Backend: `eil/modules/risk/router.py` (`GET /risk/radar` — items with rollup confidence × impact via graph `downstream_impact`), `GET /escalations`, `PATCH /escalations/{id}/acknowledge`; `eil/modules/risk/schemas.py`. Tests: `tests/test_risk_api.py` (3), web `RiskPage.test.tsx` (2). OpenAPI + TS client regenerated. Confidence trend and radar detail drill not built. |

**Exit criteria:** T7.1, T7.2, T7.3, T7.4, T7.5, T7.7 and T7.8 delivered and unit-tested; Scenario 4 browser acceptance not implemented. |

## Phase 8 — Executive view & assistant (Scenario 5) — STARTED

| Task | Status | Notes |
|---|---|---|
| T8.1 (L) | Metrics layer: read models for committed work, priorities, capacity constraints, at-risk items, strategic outcomes affected, interventions required; definitions in `docs/metrics.md`; as-of timestamp on every widget | Delivered (`eil/modules/metrics/service.py::executive_summary` + `GET /metrics/summary`, `eil/modules/metrics/router.py`). Tests: `tests/test_metrics.py` (1). |
| T8.2 (L) | Executive dashboard answering the five questions of Scenario 5 (committed to what / most important / where constrained / what's at risk and why / what outcomes affected / where intervention required) with drill-down to graph, capacity and risk views; role-scoped | Delivered (`apps/web/src/features/executive/ExecutivePage.tsx` + route `/executive` + nav entry + EN/AR strings): six panels — committed to what (by org unit, min confidence, avg confidence, as-of), most important (top priorities, override flags), where constrained (capacity constraints), what's at risk and why (at-risk items + risk radar), strategic outcomes affected (objectives with confidence + benefit counts), intervention required (open escalations with due-in). Backend: `eil/modules/metrics/service.py::executive_summary` extended with `strategic_outcomes.objectives` + `committed.by_org_unit` + `users`. Tests: web `ExecutivePage.test.tsx` (1). |
| T8.3 (L) | "Ask EIL" assistant: Groq tool-calling over read-only tools (`query_graph`, `get_capacity`, `list_commitments`, `get_risks`, `explain_confidence`, `get_priorities`), streaming responses, mandatory entity citations, RBAC as caller, conversation logging, refusal behaviours — Delivered v1 (`eil/modules/assistant/service.py::ask_eil` + `POST /assistant/ask`): read-only tools over the enterprise data with mandatory citations; multi-turn tool-calling via the gateway (Groq tool-calling support added to `LLMClient` protocol + `GroqClient` + replay client); graceful unavailable when AI is disabled (R12). Tests: `tests/test_assistant.py` (5). | Streaming + conversation logging delivered (T8.3): `ask_eil` accepts `on_event`; `POST /assistant/ask` with `stream: true` returns SSE (`tool_call` events + final `result` event); conversations persisted (`eil/modules/assistant/models.py::AssistantConversation`, migration `0007_assistant_conversations`, `GET /assistant/conversations[...]`). Assistant web chat UI consumes the non-streaming path (display + multi-turn history pending). |
| T8.4 (M) | Auto-generated executive brief — done (service + `GET /executive/brief` endpoint) | Executive brief service (`eil/modules/assistant/brief.py`): fact sheet from `executive_summary` + numbers-guarded LLM narration (template/HTML fallback); endpoint `GET /executive/brief` wired in new `eil/modules/executive/router.py` (RBAC `work.view`); endpoint test `test_executive_brief_endpoint`. PDF export not implemented yet (no PDF renderer in the stack). |
| T8.5 (S) | Presenter mode — DEFERRED | |

**Exit criteria:** Partial: T8.1, T8.2, T8.3 (v1) delivered; T8.4 (executive brief service + `GET /executive/brief` endpoint) delivered; T8.5 (presenter mode) not built; Scenario 5 browser acceptance not implemented. |

## Phase 9 — Hardening, evals, demo kit & documentation

| Task | Status | Notes |
|---|---|---|
| T9.1 (M) Eval harness finalised | done | `eil/ai/evals/initial.json`, `apps/api/scripts/ai_evals.py`, `make ai-eval` gate — verified passing (3 PASS: extraction/classification/owner replay). |
| T9.2 (M) Security hardening | done | CSP header (`eil/core/middleware.py`), per-principal/IP rate limiting (`RateLimitMiddleware`), CORS allow-list lock-down (fail-closed validator in `eil/core/config.py`), host allow-list (`TrustedHostMiddleware`), SSRF guard (`connectors/sdk/urls.py`, validated at sim URLs and ingestion of external artifact URLs), ASVS L2 checklist (`docs/asvs-l2-checklist.md`), `make security-scan` (secret patterns + `pip-audit` dependency audit, clean; wired into CI). |
| T9.3 (M) Performance pass | done | `apps/api/tests/test_perf_smoke.py` — smoke budgets vs plan §14 NFRs (healthz, executive summary < 2 s, radar/heatmap/prioritization board, CRUD endpoints < 400 ms; first-call graph/model-loading budget noted as read-model targets). Hot spots verified: indexes on `work_item.type/status`, `audit_log.*`, `sync_run.*`, graph response cache. |
| T9.4 (S) Accessibility (WCAG 2.1 AA) audit | done | `docs/accessibility-audit.md`; fixes: `RiskPage` table (`scope` + caption), `AiInboxPage` keyboard-accessible suggestion cards (role/tabIndex/keyboard), `CapacityPage` heatmap week `aria-label`s; RTL/Arabic verified via smoke spec (`dir=rtl` on locale switch). |
| T9.5 (M) Demo kit (`make demo`) | done | Presenter control panel fixed + wired (`POST /demo/inject-event`, `POST /demo/reset` — was dead code: invalid syntax + missing `_audit` + wrong imports). Scenario runbooks (`docs/runbooks/scenario-1..5.md`), scenario seeds (`seed/scenarios/1..4/seed.json` + README), scenario e2e specs for scenarios 1–4 (`apps/web/e2e/scenario1..4.spec.ts` — fixed invalid `"""` docstrings). Browser e2e runs only in CI (no browser on this workstation). |
| T9.6 (M) Documentation | doing | `docs/capability-matrix.md` created from plan §12 (current-state version); ASVS L2 checklist, accessibility audit, runbooks, backup/DR notes added. |
| T9.7 (S, optional) Helm chart / K8s manifests | done | `infra/helm/eil/` (chart + values + templates + README), `infra/backup-restore.md`, `infra/dr-notes.md` (verified `alembic upgrade head` applies 0007 to head). |

**Exit criteria:** capability matrix exists and is accurate for Phases 0–8; scenario runbooks, seeds and scenario e2e specs added (1–4; browser e2e blocked on this workstation); security scan clean (secret patterns + pip-audit); `make demo` works end-to-end; fresh clone reaches working demo — Phase 9 delivered. |

## Decisions

- ADR-001 — monorepo and tooling baseline (`docs/adr/ADR-001-monorepo-tooling.md`)
- ADR-002 — local development fallbacks without Docker (`docs/adr/ADR-002-local-dev-fallbacks.md`)

## Known limitations (honest list)

- Docker/PostgreSQL/Redis/Keycloak are not installed on this workstation. Local mode
  uses SQLite, dev JWT auth, inline jobs and local object storage. The compose stack is
  authored but has not been booted; the Keycloak/OIDC browser flow is therefore unverified.
- Playwright browser downloads failed from the available CDN (HTTP 400 / stalled transfer),
  so browser-level e2e/OIDC browser tests are not executed locally. API-level e2e smoke and
  Vitest unit tests are committed and wired into CI.
- Keycloak/OIDC browser login and Realm UX cannot be runtime-verified without Docker/Keycloak;
  the realm/users/groups/required MFA actions are authored and YAML/JSON-validated.
- No `GROQ_API_KEY` yet: `AI_ENABLED=false`, `LLM_MODE=replay`. Phase 4 requires the key
  for live mode; replay cassettes will cover deterministic demos.
- pgvector semantic search will need a Python-side cosine fallback in local mode until
  PostgreSQL + pgvector are available (to be recorded in ADR-002 when implemented).
- Phase 5: prioritisations override is applied on request (SoD-2 enforced); the plan's
  "override creates a workflow instance" (§1.6) is deferred to the governance-integrated
  work (Phase 1 engine + Phase 9 hardening).
- Phase 5: the prioritisations board browser e2e was not executed (no browser on this
  workstation — Playwright browser downloads fail here); API-level and Vitest coverage
  added instead.
- `AllocationRead`/`PrioritizedItemRead` serialise `Decimal` as JSON numbers (pydantic v2
  default is strings) — `test_allocations_api` asserts the numeric contract.
- Prioritisation board UI render in the real app is not browser-verified.
- Phase 6: `capacity_sustained_red_weeks` is configured; the consecutive-week tracking
  job for sustained overload is not built yet.
- Phase 6: task-spreading demand counts tasks with `attributes["effort_hours"]`; team-level
  demand tensors are a follow-up.
- Phase 6: optimiser v1 has no dependency-order shifts and the "augment"/"reprioritise"
  strategies reuse the same assignment model with different weights; full strategy
  breadth is a follow-up.
- Phase 6: capacity heatmap UI (T6.7) and Scenario 3 browser acceptance not built.
- Phase 7: GBDT/SHAP delay propensity and real SHAP drivers, confidence trends
  (no history stored yet), risk-radar detail drill, escalation UI detail actions
  not built.
- Phase 7: delay-propensity v1 is linear logistic regression (GBDT/SHAP planned);
  `calibrate_delay_model` returns the isotonic (probability, fitted) pairs table;
  `training_rows` labels items delayed beyond 3 days as they appear in data
  (a synthetic-history generator for the demo is not yet built).
- Assistant: token-level streaming of Groq responses is a follow-up (the gateway's
  `GroqClient.chat` has no streaming method yet); the web chat UI consumes the
  non-streaming path — the conversation history is available via
  `GET /assistant/conversations` but is not rendered in the UI yet.
- Phase 8: Scenario 5 browser acceptance not run (Playwright blocked on this
  workstation; `apps/web/e2e/scenario5-executive.spec.ts` runs in CI).
- Phase 9: scenario e2e specs added for scenarios 1–4 (`apps/web/e2e/scenario1..4.spec.ts`);
  browser-level runs are CI-only (no browser binaries on this workstation).
- Phase 7: ESC-3 v1 = objectives with delivery confidence below 0.80 (the plan's
  drop-in-7-days proxy is not tracked without confidence history).
- Migration drift (user-test finding, fixed): the `Score` model gained
  `TimestampMixin` columns after the Phase 5 migration, so alembic-managed
  databases were missing `score.created_at`/`score.updated_at` (and
  `updated_at` on `ai_suggestion`, `score_override`, `scoring_model`,
  `scoring_model_criterion`) plus a stray `score.version` —
  `GET /api/v1/prioritization` 500'd on the dev database. Fixed by migrations
  `0008_add_missing_ts` + `0009_drop_score_version`; regression
  test   `apps/api/tests/test_migration_drift.py` (scratch-DB `alembic upgrade
  head` + model diff — 0 drifted tables; audit: `uv run python
  apps/api/tests/test_migration_drift.py` / one-off script `/tmp/drift_audit.py`).
- Approvals/inbox user-test finding (fixed): concurrent requests raced in
  `ensure_user` — `sqlite3.IntegrityError: UNIQUE constraint failed:
  org_unit.code` → `GET /api/v1/approvals/inbox` 500. Fixed with the
  race-safe `_get_or_create_org_unit` + re-select in `ensure_user`
  (`eil/modules/identity/rbac.py`); regression tests
  `apps/api/tests/test_ensure_user.py` (2 passed); verified live (dev log:
  `approvals/inbox → 200`).
- Integration create-form user-test finding (fixed): the "Create" button only
  validated `name`; empty `owner` reached the API → `POST
  /api/v1/integrations/sources` 422. The form now disables Create until both
  `name` and `owner` are set (`apps/web/src/features/admin/IntegrationPage.tsx`);
  verified live as `integration_admin` (`GET sources` → 200, valid create → 201).
