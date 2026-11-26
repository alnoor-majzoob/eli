"""Core entity CRUD, state machine, optimistic concurrency and links."""

from __future__ import annotations

from httpx import AsyncClient


async def _post(client: AsyncClient, headers: dict[str, str], **payload) -> dict:
    response = await client.post("/api/v1/items", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def test_hierarchy_crud_and_state_machine(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    objective = await _post(client, pm, type="objective", title="Zero HSSE incidents")
    initiative = await _post(
        client, pm, type="initiative", title="Reliability programme", parent_id=objective["id"]
    )
    demand = await _post(
        client, pm, type="demand", title="Flare gas recovery", parent_id=initiative["id"]
    )
    task = await _post(client, pm, type="task", title="Order seal kit", parent_id=initiative["id"])

    assert objective["status"] == "draft"
    assert demand["type"] == "demand"

    activated = await client.patch(
        f"/api/v1/items/{task['id']}", json={"status": "active"}, headers=pm
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"

    completed = await client.patch(
        f"/api/v1/items/{task['id']}", json={"status": "completed"}, headers=pm
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"

    illegal = await client.patch(
        f"/api/v1/items/{task['id']}", json={"status": "active"}, headers=pm
    )
    assert illegal.status_code == 409
    assert illegal.json()["code"] == "invalid_transition"

    workflow_status = await client.patch(
        f"/api/v1/items/{task['id']}", json={"status": "submitted"}, headers=pm
    )
    assert workflow_status.status_code == 409
    assert workflow_status.json()["code"] == "conflict"


async def test_invalid_parent_type_is_rejected(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    objective = await _post(client, pm, type="objective", title="Objective")
    response = await client.post(
        "/api/v1/items",
        json={"type": "task", "title": "Bad parent", "parent_id": objective["id"]},
        headers=pm,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_etag_optimistic_concurrency(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    item = await _post(client, pm, type="task", title="Concurrency")
    fetched = await client.get(f"/api/v1/items/{item['id']}", headers=pm)
    etag = fetched.headers["etag"]
    assert etag == '"1"'

    stale = await client.patch(
        f"/api/v1/items/{item['id']}",
        json={"title": "Stale update"},
        headers={**pm, "If-Match": '"99"'},
    )
    assert stale.status_code == 412

    current = await client.patch(
        f"/api/v1/items/{item['id']}",
        json={"title": "Current update"},
        headers={**pm, "If-Match": etag},
    )
    assert current.status_code == 200
    assert current.json()["title"] == "Current update"
    assert current.headers["etag"] == '"2"'

    body_version = await client.patch(
        f"/api/v1/items/{item['id']}",
        json={"title": "Conflicting body", "version": 1},
        headers=pm,
    )
    assert body_version.status_code == 409


async def test_links_validation_and_cycle_detection(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    objective = await _post(client, pm, type="objective", title="Objective")
    task_a = await _post(client, pm, type="task", title="Task A")
    task_b = await _post(client, pm, type="task", title="Task B")

    aligns = await client.post(
        f"/api/v1/items/{task_a['id']}/links",
        json={"dst_id": objective["id"], "link_type": "aligns_to"},
        headers=pm,
    )
    assert aligns.status_code == 201, aligns.text
    link_id = aligns.json()["id"]

    duplicate = await client.post(
        f"/api/v1/items/{task_a['id']}/links",
        json={"dst_id": objective["id"], "link_type": "aligns_to"},
        headers=pm,
    )
    assert duplicate.status_code == 409

    invalid_target = await client.post(
        f"/api/v1/items/{task_a['id']}/links",
        json={"dst_id": task_b["id"], "link_type": "aligns_to"},
        headers=pm,
    )
    assert invalid_target.status_code == 422

    self_link = await client.post(
        f"/api/v1/items/{task_a['id']}/links",
        json={"dst_id": task_a["id"], "link_type": "depends_on"},
        headers=pm,
    )
    assert self_link.status_code == 422

    depends = await client.post(
        f"/api/v1/items/{task_a['id']}/links",
        json={"dst_id": task_b["id"], "link_type": "depends_on"},
        headers=pm,
    )
    assert depends.status_code == 201

    cycle = await client.post(
        f"/api/v1/items/{task_b['id']}/links",
        json={"dst_id": task_a["id"], "link_type": "depends_on"},
        headers=pm,
    )
    assert cycle.status_code == 409
    assert cycle.json()["code"] == "cycle_detected"

    outgoing = await client.get(f"/api/v1/items/{task_a['id']}/links?direction=out", headers=pm)
    assert outgoing.status_code == 200
    assert {link["link_type"] for link in outgoing.json()} == {"aligns_to", "depends_on"}

    deleted = await client.delete(f"/api/v1/items/{task_a['id']}/links/{link_id}", headers=pm)
    assert deleted.status_code == 204


async def test_delete_draft_item(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    item = await _post(client, pm, type="task", title="Disposable")
    deleted = await client.delete(f"/api/v1/items/{item['id']}", headers=pm)
    assert deleted.status_code == 204
    missing = await client.get(f"/api/v1/items/{item['id']}", headers=pm)
    assert missing.status_code == 404


async def test_mutations_are_audited(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    auditor = await auth("auditor")
    item = await _post(client, pm, type="task", title="Audited task")
    await client.patch(f"/api/v1/items/{item['id']}", json={"status": "active"}, headers=pm)
    response = await client.get(
        f"/api/v1/audit?entity_id={item['id']}&entity_type=work_item", headers=auditor
    )
    assert response.status_code == 200
    actions = {row["action"] for row in response.json()}
    assert {"work_item.created", "work_item.updated"} <= actions
    assert all(len(row["hash"]) == 64 for row in response.json())
