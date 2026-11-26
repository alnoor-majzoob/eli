"""AI Inbox API (plan §8, T4.9): list/detail/accept/reject/bulk."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from eil.ai.models import AiSuggestion
from eil.modules.execution.models import WorkItem
from eil.modules.integration.models import ApprovedSource, SourceArtifact


async def _add_suggestion(session, **fields: Any) -> AiSuggestion:
    defaults = {
        "kind": "extracted_item",
        "payload": {"title": "AI suggestion", "kind": "task", "summary": "s"},
        "model": "ai",
        "prompt_version": "detect_candidates@v1",
        "status": "pending",
    }
    defaults.update(fields)
    suggestion = AiSuggestion(**defaults)
    session.add(suggestion)
    await session.commit()
    return suggestion


async def test_ai_inbox_list_and_detail(client: AsyncClient, auth, app) -> None:
    pm = await auth("project_manager")
    async with app.state.session_factory() as session:
        source = ApprovedSource(type="m365", name="M365 demo", owner="IT", enabled=True)
        session.add(source)
        await session.flush()
        artifact = SourceArtifact(
            source_id=source.id,
            kind="meeting_transcript",
            external_id="art-1",
            title="Weekly review",
            payload={"body": "The pump on line 3 failed during yesterday's shift."},
            content_hash="abc",
            classification="internal",
            ai_processing_allowed=False,
        )
        session.add(artifact)
        await session.flush()
        suggestion = await _add_suggestion(
            session,
            payload={"title": "Replace pump", "kind": "task", "artifact_id": str(artifact.id)},
        )

    response = await client.get("/api/v1/ai/suggestions", params={"status": "pending"}, headers=pm)
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["kind"] == "extracted_item"

    response = await client.get(f"/api/v1/ai/suggestions/{suggestion.id}", headers=pm)
    assert response.status_code == 200
    detail = response.json()
    assert detail["id"] == str(suggestion.id)
    assert detail["source_excerpt"]
    assert detail["source_artifact_id"] == str(artifact.id)


async def test_ai_inbox_accept_reject_bulk(client: AsyncClient, auth, app) -> None:
    pm = await auth("project_manager")
    async with app.state.session_factory() as session:
        s1 = await _add_suggestion(session)
        s2 = await _add_suggestion(session, kind="extracted_item", payload={"title": "Second"})
        s3 = await _add_suggestion(session, kind="extracted_item", payload={"title": "Third"})

    response = await client.post(f"/api/v1/ai/suggestions/{s1.id}/accept", headers=pm)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "accepted"
    async with app.state.session_factory() as session:
        suggestion = (
            (await session.execute(select(AiSuggestion).where(AiSuggestion.id == s1.id)))
            .scalars()
            .first()
        )
        assert suggestion is not None
        assert suggestion.status == "accepted"
        assert suggestion.resulting_entity is not None
        item = (
            (
                await session.execute(
                    select(WorkItem).where(WorkItem.id == suggestion.resulting_entity)
                )
            )
            .scalars()
            .first()
        )
        assert item is not None and item.origin == "ai_extracted"

    response = await client.post(
        f"/api/v1/ai/suggestions/{s2.id}/reject",
        json={"reason": "Not actionable"},
        headers=pm,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"

    # Bulk: accept s3 + reject s1 again (already terminal → error entry).
    response = await client.post(
        "/api/v1/ai/suggestions/bulk",
        json={
            "items": [
                {"suggestion_id": str(s3.id), "action": "accept"},
                {"suggestion_id": str(s1.id), "action": "reject"},
            ]
        },
        headers=pm,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert str(s3.id) in body["accepted"]
    assert str(s1.id) in body["errors"]
