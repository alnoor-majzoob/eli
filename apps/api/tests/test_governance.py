"""Governance workflow engine, approvals inbox, SoD, delegation and escalation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import select

from eil.modules.governance.models import Approval


async def _post(client: AsyncClient, headers: dict[str, str], **payload) -> dict:
    response = await client.post("/api/v1/items", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _pending_for(client: AsyncClient, headers: dict[str, str], item_id: str) -> dict:
    response = await client.get("/api/v1/approvals?status=pending", headers=headers)
    assert response.status_code == 200, response.text
    for row in response.json()["items"]:
        if row["work_item_id"] == item_id:
            return row
    raise AssertionError("pending approval not found")


async def test_workflow_definitions_are_seeded(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    response = await client.get("/api/v1/workflows", headers=pm)
    assert response.status_code == 200
    keys = {row["key"] for row in response.json()}
    assert {
        "demand_approval",
        "stage_gate",
        "change_request",
        "priority_override",
        "scenario_promotion",
    } <= keys


async def test_demand_submit_and_approve_flow(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    portfolio = await auth("portfolio_manager")
    demand = await _post(client, pm, type="demand", title="Flare Gas Recovery Upgrade")

    submitted = await client.post(f"/api/v1/items/{demand['id']}/submit", headers=pm)
    assert submitted.status_code == 202, submitted.text
    assert submitted.json()["status"] == "submitted"

    approval = await _pending_for(client, portfolio, demand["id"])
    inbox = await client.get("/api/v1/approvals/inbox", headers=portfolio)
    assert inbox.status_code == 200
    assert any(row["id"] == approval["id"] for row in inbox.json()["items"])

    decided = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        json={"decision": "approved", "comment": "Aligned with O1/O3."},
        headers=portfolio,
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approved"

    item = await client.get(f"/api/v1/items/{demand['id']}", headers=pm)
    assert item.json()["status"] == "approved"

    instances = await client.get(
        f"/api/v1/workflow-instances?work_item_id={demand['id']}", headers=pm
    )
    assert instances.status_code == 200
    assert instances.json()[0]["status"] == "completed"


async def test_self_approval_is_blocked_and_audited(client: AsyncClient, auth, make_token) -> None:
    requester = make_token("sod-requester", ["portfolio_manager"], "pmo")
    other = await auth("portfolio_manager")
    demand = await _post(client, requester, type="demand", title="Self approval attempt")
    submitted = await client.post(f"/api/v1/items/{demand['id']}/submit", headers=requester)
    assert submitted.status_code == 202

    approval = await _pending_for(client, requester, demand["id"])
    response = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        json={"decision": "approved"},
        headers=requester,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "sod_violation"
    assert response.json()["rule"] == "SOD-1"

    auditor = await auth("auditor")
    audit = await client.get(
        "/api/v1/audit?action=approval.denied&entity_id=" + demand["id"], headers=auditor
    )
    assert audit.status_code == 200
    assert audit.json(), "denial must be audited"

    approved = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        json={"decision": "approved"},
        headers=other,
    )
    assert approved.status_code == 200, approved.text


async def test_wrong_approver_role_is_rejected(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    demand = await _post(client, pm, type="demand", title="Wrong approver")
    await client.post(f"/api/v1/items/{demand['id']}/submit", headers=pm)
    approval = await _pending_for(client, pm, demand["id"])
    response = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        json={"decision": "approved"},
        headers=pm,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


async def test_rejection_flow(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    portfolio = await auth("portfolio_manager")
    demand = await _post(client, pm, type="demand", title="Reject me")
    await client.post(f"/api/v1/items/{demand['id']}/submit", headers=pm)
    approval = await _pending_for(client, portfolio, demand["id"])
    rejected = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        json={"decision": "rejected", "comment": "Missing cost case."},
        headers=portfolio,
    )
    assert rejected.status_code == 200
    item = await client.get(f"/api/v1/items/{demand['id']}", headers=pm)
    assert item.json()["status"] == "rejected"


async def test_stage_gate_uses_department_head_scope(client: AsyncClient, auth, org_id) -> None:
    admin = await auth("admin")
    dept_head = await auth("dept_head")
    project = await _post(
        client,
        admin,
        type="project",
        title="K-201 Overhaul",
        org_unit_id=str(await org_id("ops")),
    )
    submitted = await client.post(
        f"/api/v1/items/{project['id']}/submit?workflow_key=stage_gate", headers=admin
    )
    assert submitted.status_code == 202, submitted.text
    approval = await _pending_for(client, dept_head, project["id"])
    assert approval["approver_role"] == "dept_head"
    decided = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        json={"decision": "approved"},
        headers=dept_head,
    )
    assert decided.status_code == 200, decided.text


async def test_delegation_allows_delegate_to_decide(
    client: AsyncClient, auth, make_token, user_id
) -> None:
    pm = await auth("project_manager")
    portfolio = await auth("portfolio_manager")
    demand = await _post(client, pm, type="demand", title="Delegated approval")
    await client.post(f"/api/v1/items/{demand['id']}/submit", headers=pm)
    approval = await _pending_for(client, portfolio, demand["id"])

    delegate_subject = "delegate-portfolio"
    delegate = make_token(delegate_subject, ["portfolio_manager"], "pmo")
    assert (await client.get("/api/v1/items", headers=delegate)).status_code == 200
    delegate_id = await user_id(delegate_subject)

    delegated = await client.post(
        f"/api/v1/approvals/{approval['id']}/delegate",
        json={"delegate_to": str(delegate_id)},
        headers=portfolio,
    )
    assert delegated.status_code == 200, delegated.text

    decided = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        json={"decision": "approved"},
        headers=delegate,
    )
    assert decided.status_code == 200, decided.text


async def test_overdue_approval_escalation(client: AsyncClient, app, auth) -> None:
    pm = await auth("project_manager")
    admin = await auth("admin")
    demand = await _post(client, pm, type="demand", title="Escalate me")
    await client.post(f"/api/v1/items/{demand['id']}/submit", headers=pm)

    async with app.state.session_factory() as session:
        approval = (
            await session.execute(
                select(Approval).where(Approval.work_item_id == UUID(demand["id"]))
            )
        ).scalar_one()
        approval.due_at = datetime.now(UTC) - timedelta(hours=1)
        await session.commit()

    response = await client.post("/api/v1/approvals/escalate-overdue", headers=admin)
    assert response.status_code == 200
    assert response.json()["escalated"] == 1

    async with app.state.session_factory() as session:
        refreshed = (
            await session.execute(
                select(Approval).where(Approval.work_item_id == UUID(demand["id"]))
            )
        ).scalar_one()
        assert refreshed.escalated_at is not None
