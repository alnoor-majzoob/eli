"""Enterprise Work Graph API: neighbours, lineage, path, downstream-impact, integrity."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import delete

from eil.modules.execution.models import LinkTypeRule, WorkLink


async def _post(client: AsyncClient, headers: dict[str, str], **payload: Any) -> dict[str, Any]:
    response = await client.post("/api/v1/items", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _link(
    client: AsyncClient,
    headers: dict[str, str],
    src_id: UUID,
    dst_id: UUID,
    link_type: str,
    weight: float | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"dst_id": str(dst_id), "link_type": link_type}
    if weight is not None:
        body["weight"] = weight
    response = await client.post(f"/api/v1/items/{src_id}/links", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _ids(data: Any) -> list[str]:
    return [item["id"] for item in data]


async def _setup_chain(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    objective = await _post(client, headers, type="objective", title="Zero HSSE incidents")
    project = await _post(
        client, headers, type="project", title="HSSE programme", parent_id=objective["id"]
    )
    milestone = await _post(
        client, headers, type="milestone", title="Q1 safety review", parent_id=project["id"]
    )
    task = await _post(
        client, headers, type="task", title="Order PPE kit", parent_id=milestone["id"]
    )
    await _link(client, headers, task["id"], milestone["id"], "part_of")
    await _link(client, headers, milestone["id"], project["id"], "part_of")
    await _link(client, headers, project["id"], objective["id"], "aligns_to")
    return {
        "objective": objective,
        "project": project,
        "milestone": milestone,
        "task": task,
    }


async def test_neighbours_and_virtual_assigned_to(client: AsyncClient, auth, user_id) -> None:
    pm = await auth("project_manager")
    task = await _post(client, pm, type="task", title="Order PPE kit")
    # The User row is JIT-provisioned on the first authenticated request.
    pm_id = await user_id("demo-project")
    updated = await client.patch(
        f"/api/v1/items/{task['id']}", json={"owner_id": str(pm_id)}, headers=pm
    )
    assert updated.status_code == 200, updated.text
    related = await _post(client, pm, type="task", title="Review PPE kit")

    await _link(client, pm, task["id"], related["id"], "related_to")

    response = await client.get(f"/api/v1/graph/nodes/{task['id']}/neighbors", headers=pm)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["node_id"] == task["id"]
    assert any(
        edge["link_type"] == "related_to" and edge["dst_id"] == related["id"]
        for edge in data["edges"]
    )
    virtual = [edge for edge in data["edges"] if edge["is_virtual"]]
    assert len(virtual) == 1
    assert virtual[0]["link_type"] == "assigned_to"
    assert virtual[0]["dst"]["id"] == str(pm_id)
    assert virtual[0]["src_id"] == task["id"]

    direction_in = await client.get(
        f"/api/v1/graph/nodes/{task['id']}/neighbors?direction=in", headers=pm
    )
    assert direction_in.status_code == 200
    assert direction_in.json()["edges"] == []


async def test_lineage_to_objective(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    chain = await _setup_chain(client, pm)

    response = await client.get(f"/api/v1/graph/nodes/{chain['task']['id']}/lineage", headers=pm)
    assert response.status_code == 200, response.text
    assert _ids(response.json()["items"]) == _ids(
        [chain["task"], chain["milestone"], chain["project"], chain["objective"]]
    )


async def test_path_between_nodes(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    chain = await _setup_chain(client, pm)
    island = await _post(client, pm, type="task", title="Island task")

    response = await client.get(
        "/api/v1/graph/path",
        params={"from": chain["task"]["id"], "to": chain["objective"]["id"]},
        headers=pm,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["exists"] is True
    assert _ids(data["nodes"]) == _ids(
        [chain["task"], chain["milestone"], chain["project"], chain["objective"]]
    )

    missing = await client.get(
        "/api/v1/graph/path",
        params={"from": chain["task"]["id"], "to": island["id"]},
        headers=pm,
    )
    assert missing.status_code == 200
    assert missing.json()["exists"] is False


async def test_downstream_impact(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    chain = await _setup_chain(client, pm)

    response = await client.get(
        f"/api/v1/graph/nodes/{chain['task']['id']}/downstream-impact", headers=pm
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert [item["id"] for item in data["items"]] == _ids(
        [chain["milestone"], chain["project"], chain["objective"]]
    )
    assert [item["depth"] for item in data["items"]] == [1, 2, 3]
    for item in data["items"]:
        assert Decimal(str(item["strongest_path_weight"])) == 1

    # Root with no impact: the objective is downstream of the project, not the reverse.
    empty = await client.get(
        f"/api/v1/graph/nodes/{chain['objective']['id']}/downstream-impact", headers=pm
    )
    assert empty.status_code == 200
    assert empty.json()["items"] == []


async def test_integrity_orphan_and_cycle_reports(client: AsyncClient, auth, app: FastAPI) -> None:
    pm = await auth("project_manager")
    orphan = await _post(client, pm, type="task", title="Orphan task")
    cycle_a = await _post(client, pm, type="task", title="Cycle A")
    cycle_b = await _post(client, pm, type="task", title="Cycle B")

    # depends_on cycles are rejected at insert time (service layer) — create one
    # directly via the session to exercise the integrity report.
    async with app.state.session_factory() as session:
        session.add(
            WorkLink(src_id=UUID(cycle_a["id"]), dst_id=UUID(cycle_b["id"]), link_type="depends_on")
        )
        session.add(
            WorkLink(src_id=UUID(cycle_b["id"]), dst_id=UUID(cycle_a["id"]), link_type="depends_on")
        )
        await session.commit()

    response = await client.get("/api/v1/graph/integrity", headers=pm)
    assert response.status_code == 200, response.text
    data = response.json()
    orphan_ids = {item["id"] for item in data["orphan_tasks"]}
    assert orphan["id"] in orphan_ids
    assert all(item["reason"] for item in data["orphan_tasks"])
    cycle_nodes = {node["id"] for cycle in data["depends_on_cycles"] for node in cycle["nodes"]}
    assert {cycle_a["id"], cycle_b["id"]} <= cycle_nodes
    assert data["duplicate_edges"] == []


async def test_link_type_rule_table_enforcement(client: AsyncClient, auth, app: FastAPI) -> None:
    pm = await auth("project_manager")
    objective = await _post(client, pm, type="objective", title="Objective")
    task = await _post(client, pm, type="task", title="Task")

    # First link creation seeds the whitelist (create_all flows have no migration seed).
    seeded = await client.post(
        f"/api/v1/items/{task['id']}/links",
        json={"dst_id": str(objective["id"]), "link_type": "aligns_to"},
        headers=pm,
    )
    assert seeded.status_code == 201, seeded.text

    async with app.state.session_factory() as session:
        await session.execute(
            delete(LinkTypeRule).where(
                LinkTypeRule.src_type == "task",
                LinkTypeRule.dst_type == "objective",
                LinkTypeRule.link_type == "aligns_to",
            )
        )
        await session.commit()

    task2 = await _post(client, pm, type="task", title="Task 2")
    response = await client.post(
        f"/api/v1/items/{task2['id']}/links",
        json={"dst_id": str(objective["id"]), "link_type": "aligns_to"},
        headers=pm,
    )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"
