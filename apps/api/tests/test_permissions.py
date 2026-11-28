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


async def test_me_permissions_reflects_role(client: AsyncClient, auth) -> None:
    auditor = await auth("auditor")
    response = await client.get("/api/v1/me/permissions", headers=auditor)
    assert response.status_code == 200
    body = response.json()
    assert "auditor" in body["roles"]
    assert body["permissions"].get("work.view") == "global"
    assert body["permissions"].get("audit.view") == "global"
    assert "work.edit" not in body["permissions"]  # read-only
    assert body["is_admin"] is False


async def test_me_permissions_admin_global(client: AsyncClient, auth) -> None:
    admin = await auth("admin")
    body = (await client.get("/api/v1/me/permissions", headers=admin)).json()
    assert body["is_admin"] is True
    assert body["permissions"].get("connector.manage") == "global"
    assert body["permissions"].get("rbac.admin") == "global"


async def test_me_permissions_integration_admin_minimal(client: AsyncClient, auth) -> None:
    headers = await auth("integration_admin")
    body = (await client.get("/api/v1/me/permissions", headers=headers)).json()
    assert body["permissions"].get("connector.manage") == "global"
    assert body["permissions"].get("audit.view") == "own_org"
    assert "work.view" not in body["permissions"]
    assert "dashboard.view" not in body["permissions"]


async def test_me_permissions_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/me/permissions")).status_code == 401


async def test_connectors_require_auth_and_connector_manage(client: AsyncClient, auth) -> None:
    assert (await client.get("/api/v1/integrations/connectors")).status_code == 401
    team = await auth("team_member")
    assert (await client.get("/api/v1/integrations/connectors", headers=team)).status_code == 403
    integ = await auth("integration_admin")
    assert (await client.get("/api/v1/integrations/connectors", headers=integ)).status_code == 200


async def test_allocations_require_allocation_manage(client: AsyncClient, auth) -> None:
    team = await auth("team_member")
    assert (await client.get("/api/v1/allocations", headers=team)).status_code == 403
    rm = await auth("resource_manager")
    assert (await client.get("/api/v1/allocations", headers=rm)).status_code == 200


async def test_escalation_acknowledge_requires_work_edit(client: AsyncClient, auth) -> None:
    # No escalation needed: a read-only user must be rejected before any 404.
    auditor = await auth("auditor")
    response = await client.patch(
        "/api/v1/escalations/00000000-0000-0000-0000-000000000000/acknowledge",
        headers=auditor,
    )
    assert response.status_code == 403


async def test_assistant_requires_assistant_use(client: AsyncClient, make_token) -> None:
    headers = make_token("nobody", ["no_such_role"])  # no assistant.use, no work.view
    response = await client.post(
        "/api/v1/assistant/ask", json={"question": "hi"}, headers=headers
    )
    assert response.status_code in (401, 403, 409)


async def test_cross_org_own_org_scope_filters_work(client: AsyncClient, auth, org_id) -> None:
    admin = await auth("admin")
    other = await _create(
        client, admin, type="task", title="Other org", org_unit_id=str(await org_id("pmo"))
    )
    tm = await auth("team_member")
    listing = await client.get("/api/v1/items", headers=tm)
    assert listing.status_code == 200
    assert all(row["id"] != other["id"] for row in listing.json()["items"])
    # org-less items are not visible to own_org users
    orgless = await _create(client, admin, type="task", title="Org-less")
    listing2 = await client.get("/api/v1/items", headers=tm)
    assert all(row["id"] != orgless["id"] for row in listing2.json()["items"])
