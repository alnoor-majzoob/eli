"""Audit visibility, request filters, export and tamper evidence."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


async def _create_task(client: AsyncClient, auth) -> dict:
    pm = await auth("project_manager")
    response = await client.post(
        "/api/v1/items", json={"type": "task", "title": "Audit trail task"}, headers=pm
    )
    assert response.status_code == 201, response.text
    await client.patch(
        f"/api/v1/items/{response.json()['id']}",
        json={"status": "active"},
        headers=pm,
    )
    return response.json()


async def test_chain_verifies_and_serializes(client: AsyncClient, auth) -> None:
    await _create_task(client, auth)
    auditor = await auth("auditor")
    response = await client.get("/api/v1/audit/verify", headers=auditor)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["rows"] >= 2

    listing = await client.get("/api/v1/audit", headers=auditor)
    assert listing.status_code == 200
    entries = listing.json()
    assert entries
    assert all(len(entry["hash"]) == 64 for entry in entries)
    first = entries[-1]
    assert first["prev_hash"] is None
    second = entries[-2]
    assert second["prev_hash"] == first["hash"]


async def test_filters_and_csv_export(client: AsyncClient, auth) -> None:
    item = await _create_task(client, auth)
    auditor = await auth("auditor")
    filtered = await client.get(
        f"/api/v1/audit?action=work_item.created&entity_id={item['id']}",
        headers=auditor,
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["action"] == "work_item.created"

    export = await client.get("/api/v1/audit/export.csv", headers=auditor)
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    lines = export.text.strip().splitlines()
    assert lines[0].startswith("seq,ts,actor_id")
    assert ",hash" in lines[0]
    assert len(lines) > 1


async def test_append_only_triggers_block_update_and_delete(client: AsyncClient, app, auth) -> None:
    await _create_task(client, auth)
    engine = app.state.engine
    async with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            await connection.execute(text("UPDATE audit_log SET reason = 'tampered'"))
    async with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            await connection.execute(text("DELETE FROM audit_log"))


async def test_verify_detects_bypassed_tampering(client: AsyncClient, app, auth) -> None:
    await _create_task(client, auth)
    engine = app.state.engine
    async with engine.begin() as connection:
        await connection.execute(text("DROP TRIGGER audit_log_no_update"))
        await connection.execute(text("UPDATE audit_log SET reason = 'tampered' WHERE seq = 1"))

    auditor = await auth("auditor")
    response = await client.get("/api/v1/audit/verify", headers=auditor)
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["broken_at"] is not None


async def test_own_org_auditor_cannot_query_other_actors(client: AsyncClient, auth) -> None:
    integration_admin = await auth("integration_admin")
    response = await client.get("/api/v1/audit?actor_id=demo-project", headers=integration_admin)
    assert response.status_code == 403
