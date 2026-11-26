"""Integration module (plan §10, Phase 3): registry, source registry + SoD-4,
ingestion, sync, write-back, webhooks."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import connectors
from connectors.sdk import get_connector
from connectors.sdk.protocol import ConnectorCapabilities, RawRecord
from connectors.sdk.registry import (
    BaseConnector,
    register,
)
from httpx import AsyncClient
from sqlalchemy import select

from eil.main import create_app  # noqa: F401  (import order: registers connectors)
from eil.modules.execution.models import WorkItem, WorkType
from eil.modules.integration.ingestion import upsert_record
from eil.modules.integration.models import (
    ApprovedSource,
    ExternalRef,
    SyncConflict,
    WriteBackChange,
)

REPO_ROOT = Path(connectors.__file__).resolve().parents[1]


class FakeConnector(BaseConnector):
    """Deterministic in-memory connector used by the sync/ingestion tests."""

    system = "p6-fake"
    mapping_path = REPO_ROOT / "connectors" / "mappings" / "p6.yaml"
    default_mode = "sim"
    pushed: list[dict[str, Any]] = []

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            system="p6-fake", record_types=("activity",), modes=("sim",), default_mode="sim"
        )

    def pull(self, since_cursor: str | None = None):
        records = [
            RawRecord(
                external_id="fake-1",
                canonical_type="activity",
                payload={
                    "activity_code": "FA-1",
                    "activity_name": "Fake one",
                    "activity_status": "Scheduled",
                    "start_date": "2026-10-01",
                },
            ),
            RawRecord(
                external_id="fake-2",
                canonical_type="activity",
                payload={
                    "activity_code": "FA-2",
                    "activity_name": "Fake two",
                    "activity_status": "Scheduled",
                    "start_date": "2026-10-02",
                },
            ),
        ]
        if since_cursor:
            records = [r for r in records if r.external_id > since_cursor]
        yield from records

    def push(self, change: dict[str, Any]) -> None:
        type(self).pushed.append(change)


register(FakeConnector)


async def _create_source(
    client: AsyncClient, headers: dict[str, str], *, source_type: str = "p6-fake", **extra: Any
) -> dict[str, Any]:
    payload = {"type": source_type, "name": f"{source_type}-{id(client) & 0xFFFF}", "owner": "IT"}
    payload.update(extra)
    response = await client.post("/api/v1/integrations/sources", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def test_connector_registry_lists_sims(client: AsyncClient) -> None:
    response = await client.get("/api/v1/integrations/connectors")
    assert response.status_code == 200
    connectors_by_system = {entry["system"]: entry for entry in response.json()}
    for system in ("p6", "eam", "erp", "hr", "m365"):
        entry = connectors_by_system[system]
        assert entry["mode"] == "sim"
        assert entry["push_supported"] is True
        assert entry["capabilities"]["record_types"]
        assert entry["capabilities"]["default_mode"] == "sim"


async def test_source_registry_crud_and_sod4(client: AsyncClient, auth) -> None:
    pm = await auth("integration_admin")

    source = await _create_source(client, pm, ai_processing_allowed=False)
    assert source["enabled"] is True
    source_id = source["id"]

    # SoD-4: protected change without a distinct second approver → 403.
    denied = await client.patch(
        f"/api/v1/integrations/sources/{source_id}",
        json={"ai_processing_allowed": True},
        headers=pm,
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["code"] == "sod_violation"

    # SoD-4: protected change with a distinct approver → 200.
    approved = await client.patch(
        f"/api/v1/integrations/sources/{source_id}",
        json={
            "ai_processing_allowed": True,
            "approved_by": "demo-admin",
            "reason": "two-person rule",
        },
        headers=pm,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["ai_processing_allowed"] is True

    # SoD-4: self-approval is still a violation.
    self_approved = await client.patch(
        f"/api/v1/integrations/sources/{source_id}",
        json={"owned_fields": ["title"], "approved_by": "demo-integration"},
        headers=pm,
    )
    assert self_approved.status_code == 403
    assert self_approved.json()["code"] == "sod_violation"

    # Unprotected changes work without a second approver.
    renamed = await client.patch(
        f"/api/v1/integrations/sources/{source_id}",
        json={"name": "Renamed source"},
        headers=pm,
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed source"

    # Disable, then delete.
    disabled = await client.patch(
        f"/api/v1/integrations/sources/{source_id}", json={"enabled": False}, headers=pm
    )
    assert disabled.status_code == 200
    deleted = await client.delete(f"/api/v1/integrations/sources/{source_id}", headers=pm)
    assert deleted.status_code == 204

    unknown = await client.post(
        "/api/v1/integrations/sources",
        json={"type": "no-such-system", "name": "Nope", "owner": "IT"},
        headers=pm,
    )
    assert unknown.status_code == 422


async def test_sync_now_ingests_from_connector(client: AsyncClient, auth, app) -> None:
    pm = await auth("integration_admin")
    source = await _create_source(client, pm, source_type="p6-fake")

    response = await client.post(f"/api/v1/integrations/sources/{source['id']}/sync", headers=pm)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["status"] == "succeeded"
    assert run["records_count"] == 2
    assert run["triggered_by"] == "api"

    async with app.state.session_factory() as session:
        items = (
            (await session.execute(select(WorkItem).where(WorkItem.type == WorkType.TASK)))
            .scalars()
            .all()
        )
        fake_items = [item for item in items if item.attributes.get("source_type") == "p6-fake"]
        assert sorted(item.attributes.get("canonical_type") for item in fake_items) == [
            "activity",
            "activity",
        ]
        assert all(item.origin == "external" for item in fake_items)
        refs = (
            (await session.execute(select(ExternalRef).where(ExternalRef.system == "p6-fake")))
            .scalars()
            .all()
        )
        assert {ref.external_id for ref in refs} == {"fake-1", "fake-2"}
        assert all(ref.owned_fields == ["*"] for ref in refs)

        fetched = (
            await session.execute(
                select(ApprovedSource).where(ApprovedSource.id == UUID(source["id"]))
            )
        ).scalar_one()
        assert fetched.sync_cursor == "fake-2"
        assert fetched.last_sync_at is not None

    status = await client.get(f"/api/v1/integrations/sources/{source['id']}/status", headers=pm)
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["health"] == "ok"
    assert body["conflicts_unresolved"] == 0

    # Sync is idempotent: nothing new to ingest.
    again = await client.post(f"/api/v1/integrations/sources/{source['id']}/sync", headers=pm)
    assert again.status_code == 200
    assert again.json()["records_count"] == 0


async def test_reconciliation_conflicts_and_owned_fields(app) -> None:
    async with app.state.session_factory() as session:
        source = ApprovedSource(
            type="p6-fake", name="P6 Fake owned", owner="IT", owned_fields=["title"]
        )
        session.add(source)
        await session.flush()
        connector = get_connector("p6-fake")

        raw = RawRecord(
            external_id="fake-1",
            canonical_type="activity",
            payload={
                "activity_code": "FA-1",
                "activity_name": "Fake one",
                "activity_status": "Scheduled",
            },
        )
        item = await upsert_record(session, source, connector, raw)
        assert item is not None
        assert item.title == "Fake one"

        # Title is owned by the system → applied; status is not → conflict logged.
        updated = RawRecord(
            external_id="fake-1",
            canonical_type="activity",
            payload={
                "activity_code": "FA-1",
                "activity_name": "Renamed by system",
                "activity_status": "Complete",
            },
        )
        await upsert_record(session, source, connector, updated)
        await session.refresh(item)
        assert item.title == "Renamed by system"
        assert item.status == "active"  # not owned → local value kept

        conflicts = (
            (await session.execute(select(SyncConflict).where(SyncConflict.source_id == source.id)))
            .scalars()
            .all()
        )
        assert any(conflict.field == "status" for conflict in conflicts)


async def test_webhook_receiver_ingests(client: AsyncClient, auth) -> None:
    pm = await auth("integration_admin")
    source = await _create_source(client, pm, source_type="p6-fake")

    response = await client.post(
        "/api/v1/integrations/webhooks/p6-fake/manual-1",
        json={
            "type": "activity",
            "activity_code": "WH-1",
            "activity_name": "Webhook item",
            "activity_status": "Scheduled",
        },
        headers=pm,
    )
    assert response.status_code == 200, response.text
    assert response.json()["system"] == "p6-fake"
    assert response.json()["accepted"] == 1

    status = await client.get(f"/api/v1/integrations/sources/{source['id']}/status", headers=pm)
    assert status.status_code == 200


async def test_writeback_framework_default_off_and_flow(
    client: AsyncClient, auth, app, user_id
) -> None:
    pm = await auth("integration_admin")
    item = await _post_task(client, await auth("project_manager"))
    source = await _create_source(client, pm, source_type="p6-fake", write_back_enabled=False)

    # Default off: submit returns 409 (nothing queued).
    off = await client.post(
        f"/api/v1/integrations/sources/{source['id']}/writebacks",
        json={
            "action": "create_task",
            "work_item_id": item["id"],
            "payload": {"title": "Write-back task"},
        },
        headers=pm,
    )
    assert off.status_code == 409

    # Enabled + allow-list: submit → approve → execute.
    enabled = await client.patch(
        f"/api/v1/integrations/sources/{source['id']}",
        json={
            "write_back_enabled": True,
            "write_back_fields": ["create_task"],
            "approved_by": "demo-admin",
            "reason": "soD-4",
        },
        headers=pm,
    )
    assert enabled.status_code == 200, enabled.text

    submitted = await client.post(
        f"/api/v1/integrations/sources/{source['id']}/writebacks",
        json={
            "action": "create_task",
            "work_item_id": item["id"],
            "payload": {"title": "Write-back task"},
        },
        headers=pm,
    )
    assert submitted.status_code == 201, submitted.text
    change_id = submitted.json()["id"]

    approved = await client.post(
        f"/api/v1/integrations/sources/{source['id']}/writebacks/{change_id}/approve",
        headers=pm,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    executed = await client.post(
        f"/api/v1/integrations/sources/{source['id']}/writebacks/{change_id}/execute",
        headers=pm,
    )
    assert executed.status_code == 204

    async with app.state.session_factory() as session:
        change = (
            await session.execute(
                select(WriteBackChange).where(WriteBackChange.id == UUID(change_id))
            )
        ).scalar_one()
        assert change.status == "executed"
    assert FakeConnector.pushed
    assert FakeConnector.pushed[0]["action"] == "create_task"


async def _post_task(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/items", json={"type": "task", "title": "Write-back target"}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()
