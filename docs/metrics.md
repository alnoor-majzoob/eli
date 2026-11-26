# Executive metrics — definitions (plan Phase 8, T8.1)

Every executive summary widget carries an `as_of` timestamp — the read time of
`GET /metrics/summary` (`eil/modules/metrics/router.py`). Definitions:

- `committed.total` — open commitments (type `commitment`, status not completed/cancelled).
- `committed.avg_confidence` — mean delivery confidence of open commitments
  (`work_item.delivery_confidence`, written by the risk engine, plan §7.3).
- `committed.by_org_unit` — open commitments grouped by `work_item.org_unit_id`
  with the minimum confidence in the group (v1 grouping; objective grouping
  lands with Scenario 5, plan §11.5).
- `priorities` — top 20 work items (`demand`/`project`/`objective`) with rollup
  confidence, sorted by confidence desc; `override` = has a `score_override` row.
- `capacity_constraints` — top 10 overload rows (plan §9.2; RAG: red > 1.00, amber > 0.85).
- `at_risk` — open commitments/projects/milestones/objectives/initiatives with
  `delivery_confidence < 0.50` (RAG-red threshold, plan §9.5).
- `strategic_outcomes.benefits_total` — count of benefit work items (type `benefit`).
- `interventions` — open escalations (`acknowledged_at` NULL), ordered by due date.

Refresh: served on demand from `GET /metrics/summary` (v1).
