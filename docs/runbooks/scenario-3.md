# Scenario 3 — Resource Conflict (plan §11.3)

Runbook for the presenter driving Scenario 3 (deterministic replay, `make demo`).

Prereq: seeded demo state (`make seed-demo`), API on `http://127.0.0.1:8000`.

## Presenter actions

| Step | Action |
|---|---|
| 1 | Open the capacity heatmap (`/capacity`): the rotating equipment engineer shows red for weeks 12–14 (~130 % utilisation) |
| 2 | Drill into the conflict: the three competing items are listed, with impacted commitments/objectives |
| 3 | Request optimiser recommendations: four options (reassign / resequence / reprioritise / augment) with quantified deltas |
| 4 | Open the what-if workbench: apply option A, tweak dates, compare metrics vs baseline |
| 5 | Promote the chosen scenario through approval (SoD-6) |

## System behaviour

| # | Behaviour |
|---|---|
| 1 | Heatmap = `GET /capacity/heatmap`: weeks where `utilisation > 1.00` render red/amber per `capacity_red_pct`/`capacity_amber_pct` |
| 2 | Conflicts: `GET /capacity/conflicts` — roots = allocation work items; per-root `downstream_impact` graph query with criticality weighting |
| 3 | Optimiser: CP-SAT (`ortools`) over `x[task, resource, week]`; weekly capacity constraint `≤ available − baseline_demand`; `STRATEGY_WEIGHTS` per strategy; `_deltas` (unmet/overload/reassignment hours) |
| 4 | What-if: `Scenario` + `ScenarioChange` overlay; engine read-through (`scenario_id`); promote applies overlay + audits `scenario.promoted` |
| 5 | Promote requires approval by a different role (SoD-6); baseline updated atomically on promote |

## Assertions (API-level; covered by `tests/test_capacity*.py`)

- Heatmap shows red weeks for the overloaded resource in the seeded scenario
- Conflict drill lists affected commitments/objectives matching the graph downstream query
- Optimiser options respect eligibility, float and locks
- What-if metrics delta vs baseline; baseline unchanged until promote
- Scenario promote (SoD-6) updates baseline; audit trail records it

## Known gaps (PROGRESS honest list)

- Optimiser v1: no dependency-order shifts; "augment"/"reprioritise" reuse the assignment model with different weights (strategy breadth follow-up).
- Full Scenario 3 browser acceptance is not implemented (Playwright blocked on this workstation).
- Escalation/ack UI for Scenario 3 conflicts not built (Phase 6 exit).
