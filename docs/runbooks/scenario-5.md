# Scenario 5 — Executive Enterprise View (plan §11.5)

Runbook for the presenter driving Scenario 5 (deterministic replay, `make demo`).

Prereq: seeded demo state (`make seed-demo`), API on `http://127.0.0.1:8000`.
The browser-level e2e is `apps/web/e2e/scenario5-executive.spec.ts` (runs in CI).

## Presenter actions

| Step | Action |
|---|---|
| 1 | Open the executive view (`/executive`): answers — what are we committed to / most important / where constrained / at risk & why / strategic outcomes affected / where intervention required |
| 2 | Open the risk radar: at-risk items with confidence × impact; coloured by risk score |
| 3 | Open presenter mode (`/executive/presenter`): full-screen, as-of replay, auto-refresh toggle |
| 4 | Ask EIL (`/assistant`): free-form question → answer with mandatory entity citations (RBAC respected) |
| 5 | Open the executive brief (`GET /executive/brief`): auto-generated brief with numbers guard |

## System behaviour

| # | Behaviour |
|---|---|
| 1 | `executive_summary` read model: commitments (by org unit, min/avg confidence, as-of), priorities (top + overrides), capacity constraints, at-risk + drivers, strategic outcomes, interventions — role-scoped |
| 2 | Risk radar: `GET /risk/radar` — items with rollup confidence × impact, sorted by risk score; triangle cells: green/amber/red |
| 3 | Presenter mode: same panels full-screen + as-of input (live or replay) + auto-refresh |
| 4 | Ask EIL: `POST /assistant/ask` — Groq tool-calling over read-only tools (`query_graph`, `get_capacity`, `list_commitments`, `get_risks`, `explain_confidence`, `get_priorities`); mandatory citations; graceful unavailability when AI is off |
| 5 | Executive brief: `eil/modules/assistant/brief.py` — fact sheet from summary + numbers-guarded LLM narration |

## Assertions (e2e + API)

- Executive panels match `GET /metrics/summary` values (`Commitments: N`, `Benefits: N`)
- Presenter mode replays as-of; auto-refresh toggles |
- Ask EIL: graceful 409 when AI disabled; 403 for roles without access; claims carry resolvable citations

## Known gaps (PROGRESS honest list)

- Streaming + conversation logging (T8.3 — deferred).
- Scenario 5 browser acceptance not run (Playwright blocked on this workstation).
- PDF export of the brief not implemented.
