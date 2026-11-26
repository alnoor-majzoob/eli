"""RBAC/ABAC policy tests: no unauthenticated or unauthorised path."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _create(client: AsyncClient, headers: dict[str, str], **payload) -> dict:
    response = await client.post("/api/v1/items", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/items"),
        ("get", "/api/v1/dashboard"),
        ("get", "/api/v1/approvals"),
        ("get", "/api/v1/audit"),
        ("get", "/api/v1/workflows"),
    ],
)
async def test_endpoints_require_authentication(
    client: AsyncClient, method: str, path: str
) -> None:
    response = await getattr(client, method)(path)
    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


async def test_demand_creation_requires_demand_permission(client: AsyncClient, auth) -> None:
    resource_manager = await auth("resource_manager")
    response = await client.post(
        "/api/v1/items",
        json={"type": "demand", "title": "No demand permission"},
        headers=resource_manager,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    assert {"work.edit", "demand.create"} <= set(response.json()["permissions"])


async def test_executive_can_create_demand_but_not_edit_projects(client: AsyncClient, auth) -> None:
    executive = await auth("executive")
    demand = await client.post(
        "/api/v1/items",
        json={"type": "demand", "title": "Executive demand"},
        headers=executive,
    )
    assert demand.status_code == 201
    project = await client.post(
        "/api/v1/items",
        json={"type": "project", "title": "Executive project"},
        headers=executive,
    )
    assert project.status_code == 403


async def test_team_member_can_create_project_in_own_org(client: AsyncClient, auth, org_id) -> None:
    team_member = await auth("team_member")
    project = await _create(
        client,
        team_member,
        type="project",
        title="Maintenance project",
        org_unit_id=str(await org_id("pmo")),
    )
    assert project["org_unit_id"] == str(await org_id("maintenance"))


async def test_dashboard_visibility(client: AsyncClient, auth) -> None:
    integration_admin = await auth("integration_admin")
    assert (await client.get("/api/v1/dashboard", headers=integration_admin)).status_code == 403
    auditor = await auth("auditor")
    assert (await client.get("/api/v1/dashboard", headers=auditor)).status_code == 200
    executive = await auth("executive")
    assert (await client.get("/api/v1/dashboard", headers=executive)).status_code == 200


async def test_audit_visibility(client: AsyncClient, auth) -> None:
    project_manager = await auth("project_manager")
    assert (await client.get("/api/v1/audit", headers=project_manager)).status_code == 403
    auditor = await auth("auditor")
    assert (await client.get("/api/v1/audit", headers=auditor)).status_code == 200
    integration_admin = await auth("integration_admin")
    assert (await client.get("/api/v1/audit", headers=integration_admin)).status_code == 200


async def test_org_scoping_hides_other_org_items(client: AsyncClient, auth, org_id) -> None:
    admin = await auth("admin")
    maintenance = await _create(
        client,
        admin,
        type="task",
        title="Maintenance task",
        org_unit_id=str(await org_id("maintenance")),
    )
    project_manager = await auth("project_manager")
    response = await client.get(f"/api/v1/items/{maintenance['id']}", headers=project_manager)
    assert response.status_code == 404

    listing = await client.get("/api/v1/items", headers=project_manager)
    assert listing.status_code == 200
    assert listing.json()["total"] == 0


async def test_auditor_combination_is_rejected(client: AsyncClient, make_token) -> None:
    mixed = make_token("mixed-identity", ["auditor", "team_member"])
    response = await client.get("/api/v1/dashboard", headers=mixed)
    assert response.status_code == 409
    assert response.json()["code"] == "sod_violation"
    assert response.json()["rule"] == "SOD-5"
