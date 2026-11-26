"""Phase 1 exit criterion: objective to approved demand with tamper-evident audit."""

from __future__ import annotations

from httpx import AsyncClient


async def test_phase1_exit_flow(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    portfolio = await auth("portfolio_manager")
    auditor = await auth("auditor")

    objective = await client.post(
        "/api/v1/items",
        json={"type": "objective", "title": "Reduce unplanned downtime by 20%"},
        headers=pm,
    )
    assert objective.status_code == 201
    initiative = await client.post(
        "/api/v1/items",
        json={
            "type": "initiative",
            "title": "Predictive maintenance rollout",
            "parent_id": objective.json()["id"],
        },
        headers=pm,
    )
    assert initiative.status_code == 201
    demand = await client.post(
        "/api/v1/items",
        json={
            "type": "demand",
            "title": "Vibration sensors for rotating equipment",
            "parent_id": initiative.json()["id"],
            "priority_tier": 1,
        },
        headers=pm,
    )
    assert demand.status_code == 201
    item_id = demand.json()["id"]

    submitted = await client.post(f"/api/v1/items/{item_id}/submit", headers=pm)
    assert submitted.status_code == 202, submitted.text
    assert submitted.json()["status"] == "submitted"

    inbox = await client.get("/api/v1/approvals/inbox", headers=portfolio)
    assert inbox.status_code == 200
    approval = next(row for row in inbox.json()["items"] if row["work_item_id"] == item_id)

    decided = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        json={"decision": "approved", "comment": "Business case accepted."},
        headers=portfolio,
    )
    assert decided.status_code == 200, decided.text

    approved = await client.get(f"/api/v1/items/{item_id}", headers=pm)
    assert approved.json()["status"] == "approved"

    chain = await client.get("/api/v1/audit/verify", headers=auditor)
    assert chain.status_code == 200
    assert chain.json()["ok"] is True

    audit = await client.get(f"/api/v1/audit?entity_id={item_id}", headers=auditor)
    actions = {row["action"] for row in audit.json()}
    assert {"work_item.created", "work_item.submitted", "work_item.approved"} <= actions

    dashboard = await client.get("/api/v1/dashboard", headers=portfolio)
    assert dashboard.status_code == 200
    assert dashboard.json()["pending_approvals"] == 0
