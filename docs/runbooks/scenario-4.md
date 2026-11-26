# Scenario 4 — Cross-System Execution Risk (plan §11.4)

Runbook for the presenter driving Scenario 4 (deterministic replay, `make demo`).

Prereq: seeded demo state (`make seed-demo`) + simulators running
(`make mocks`: p6:9101, eam:9102, erp:9103, hr:9104, m365:9105).

## Presenter actions

| Step | Action |
|---|---|
| 1 | Presenter injects in `eam-sim`: rotor repair work order slips 3 weeks (`POST /demo/inject-event`) |
| 2 | Open the **impact cascade** view: path from the work order to the K-201 overhaul milestone → turnaround critical path → commitment → reliability objective |
| 3 | Show delivery confidence before/after: Monte Carlo recomputed on the affected subnetwork |
| 4 | Show why: SHAP/driver explanation + narrative (numbers ⊆ fact sheet) |
| 5 | Show the escalation: ESC-1/ESC-3 fire with recommended interventions |
| 6 | Manager acknowledges and creates a mitigation task: tracked in the graph; confidence trend annotated |

## System behaviour

| # | Behaviour |
|---|---|
| 1 | Webhook push from `eam-sim` (or ≤ 60 s beat sync): work item updated with `external_ref` + SIM badge |
| 2 | Graph `downstream_impact` from the root: work order → milestone → commitment → objective |
| 3 | Confidence: `recalc_confidence` recomputes delivery confidence for affected items; risk radar + drivers shown |
| 4 | Explain: `explain_confidence` fact sheet + LLM narration with numbers guard (template fallback in replay/AI-off) |
| 5 | Escalations: `generate_escalations` (ESC-1/ESC-2/3/4 rules); `GET /escalations`, acknowledge via `PATCH /escalations/{id}/acknowledge` |
| 6 | Mitigation task: created with `mitigates` link + audit; confidence trend annotated |

## Assertions (API-level; covered by `tests/test_risk_api.py`, `tests/test_risk_service.py`, `tests/test_risk_montecarlo.py`)

- External event → work item ≤ 60 s (NFR §14)
- Impact set matches graph query; confidence decreases on slippage |
- Drivers list includes the slipped work order (fact-sheet seeded drivers)
- Escalation exists with target role, due date, status open → acknowledged transition
- Monte Carlo: P50/P80/P90, delivery confidence, criticality index |

## Known gaps (PROGRESS honest list)

- Confidence trends (no history stored yet); radar detail drill; escalation UI detail actions.
- ESC-3 v1 = objectives with delivery confidence below 0.80.
- `confidence_changed` events are not yet emitted (T7.5 — wired in Phase 9).
