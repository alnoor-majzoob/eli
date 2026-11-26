"""Departmental dashboard aggregates and scope."""

from __future__ import annotations

from datetime import date, timedelta

from httpx import AsyncClient


async def _post(client: AsyncClient, headers: dict[str, str], **payload) -> dict:
    response = await client.post("/api/v1/items", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def test_dashboard_counts_and_highlights(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    next_week = (date.today() + timedelta(days=7)).isoformat()

    project = await _post(client, pm, type="project", title="Late project", planned_end=yesterday)
    await _post(client, pm, type="milestone", title="Upcoming gate", planned_end=next_week)
    demand = await _post(client, pm, type="demand", title="Pending demand")
    submitted = await client.post(f"/api/v1/items/{demand['id']}/submit", headers=pm)
    assert submitted.status_code == 202

    response = await client.get("/api/v1/dashboard", headers=pm)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["by_type"] == {"project": 1, "milestone": 1, "demand": 1}
    assert body["overdue"] == 1
    assert body["rag"]["red"] == 1
    assert [item["id"] for item in body["upcoming_milestones"]] == [
        (await client.get("/api/v1/items?type=milestone", headers=pm)).json()["items"][0]["id"]
    ]
    assert [item["id"] for item in body["pending_demands"]] == [demand["id"]]
    assert body["pending_approvals"] == 0
    assert body["recent_items"][0]["id"] == demand["id"]
    assert project["id"] in {item["id"] for item in body["recent_items"]}

    portfolio = await auth("portfolio_manager")
    portfolio_dashboard = await client.get("/api/v1/dashboard", headers=portfolio)
    assert portfolio_dashboard.status_code == 200
    assert portfolio_dashboard.json()["pending_approvals"] == 1
