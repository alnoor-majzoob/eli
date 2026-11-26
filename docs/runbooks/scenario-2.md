# Scenario 2 — Strategic Demand to Delivery (plan §11.2)

Runbook for the presenter driving Scenario 2 (deterministic replay, `make demo`).

Prereq: seeded demo state (`make seed-demo`), API on `http://127.0.0.1:8000`.

## Presenter actions

| Step | Action |
|---|---|
| 1 | Submit demand "Flare Gas Recovery Upgrade" (requester ≠ approver, SoD-2) |
| 2 | Run AI-assisted scoring; edit two criteria, verify the score recalculates deterministically |
| 3 | Open the prioritisation board (`/prioritization`): demand ranked, cut-line visible |
| 4 | Approver tries to override the tier with justification as the requester → expect `403 sod_violation` |
| 5 | Portfolio Board approves; one approver overrides the tier with justification |
| 6 | Auto-create the program/project from the delivery template (WBS, milestones, gates, benefits) |
| 7 | Bind to the `p6-sim` project; sync milestones (baseline vs forecast) |

## System behaviour

| # | Behaviour |
|---|---|
| 1 | `demand.aligns_to` objective via the AI proposal + human confirmation |
| 2 | `score_assist@v1` proposals; score always recomputed by the deterministic engine (R3) |
| 3 | Rank + cut-line from `compute_score`; `ScoreOverride` rows preserve `original_tier`; every override audited (`priority.overridden`) |
| 4 | Auto-create entities from `convert_demand_to_delivery` with alignment links + scores |
| 5 | `p6.py` binding: project ↔ `p6-sim` binding, activities → milestones, baseline vs forecast variance |
| 6 | Approval is the existing approvals workflow (demand approval, SoD-2 enforced) |

## Assertions (API-level)

- Demand → objective link exists (`aligns_to`)
- Board rank/cut-line consistent with the scoring engine (`compute_score`)
- Self-approval blocked: `403 sod_violation`; original tier preserved; `priority.overridden` audited
- Override audited with calculated vs overridden values
- Program/project created with WBS/milestones/benefits and alignment links
- P6 binding: `external_ref` present; baseline/forecast variance computed

## Known gaps (PROGRESS honest list)

- Prioritisation override creates a workflow instance — deferred (Phase 1/T9 hardening).
- Override is applied on request (SoD-2 enforced); full workflow-instance integration pending.
