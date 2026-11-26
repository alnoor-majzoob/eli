# Seed scenarios

Documented seeded starting states for the demo kit (plan §11: "seeded
starting state (`seed/scenarios/<n>/`)"). Files are JSON; see `seed.json`
per scenario. Runbooks: `docs/runbooks/scenario-<n>.md`.

| Scenario | Seed | Runbook |
|---|---|---|
| 1 — Meeting/Email to Execution | `1/seed.json` | `docs/runbooks/scenario-1.md` |
| 2 — Strategic Demand to Delivery | `2/seed.json` | `docs/runbooks/scenario-2.md` |
| 3 — Resource Conflict | `3/seed.json` | `docs/runbooks/scenario-3.md` |
| 4 — Cross-System Execution Risk | `4/seed.json` | `docs/runbooks/scenario-4.md` |

A scenario seed documents the entities present in the seeded database after
`make seed-demo` — the objective, demand and work items (with alignment and
duplicate links), allocations, and simulator records for the given system.
Scenario 5 has no seed file: it runs against the standard seeded demo state
(`make seed-demo`) and is accepted by the browser e2e
(`apps/web/e2e/scenario5-executive.spec.ts`).
