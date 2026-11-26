"""Scenario 1 acceptance (plan §10, Phase 4): artifact → extraction → promotion.

Replay mode: the ``detect_candidates`` + ``structure_items`` cassettes are
registered against the real prompts (``<name>@v1``), so the pipeline is
deterministic. Accepting the extracted-item suggestion creates a ``task`` with
a ``derived_from`` link and the ``ai_suggestion`` back-reference.
"""

from __future__ import annotations

import json

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from eil.ai.gateway import get_gateway
from eil.ai.gateway.telemetry import hash_request
from eil.ai.models import AiSuggestion
from eil.ai.pipeline.runner import run_ai_analysis
from eil.ai.prompts.registry import prompt_registry
from eil.ai.schemas import DetectCandidatesOutput
from eil.modules.execution.models import WorkItem, WorkLink
from eil.modules.integration.models import ApprovedSource, SourceArtifact

TEST_TRANSCRIPT = """1:00:00.000 --> 1:00:03.000
Aisha: The pump on line 3 failed during yesterday's shift.
1:00:03.500 --> 1:00:06.000
Mariam: We need to replace the assembly by Friday.
"""

DETECT_CASSETTE = {
    "candidates": [
        {
            "title": "Replace pump assembly on line 3",
            "kind": "task",
            "summary": "Replace the failed pump assembly on line 3",
            "evidence_quote": "The pump on line 3 failed during yesterday's shift.",
            "speaker": "Aisha",
            "confidence": 0.95,
        }
    ]
}

STRUCTURE_CASSETTE = {
    "items": [
        {
            "title": "Replace pump assembly on line 3",
            "summary": "Replace the failed pump assembly on line 3",
            "kind": "task",
            "evidence_quote": "The pump on line 3 failed during yesterday's shift.",
            "speaker": "Aisha",
            "confidence": 0.95,
        }
    ]
}


def _register_cassettes() -> None:
    gateway = get_gateway()
    detect_prompt = prompt_registry.get("detect_candidates")
    messages = detect_prompt.build_messages({"artifact_text": TEST_TRANSCRIPT})
    key = hash_request(messages, gateway.client().model_id("fast"))
    gateway.replay.register(key, json.dumps(DETECT_CASSETTE))

    structure_prompt = prompt_registry.get("structure_items")
    detect_result = DetectCandidatesOutput.model_validate_json(
        gateway.replay._cassettes[key]["response"]
    )
    structure_input = {
        "candidates_json": json.dumps(
            [candidate.model_dump() for candidate in detect_result.candidates]
        )
    }
    structure_messages = structure_prompt.build_messages(structure_input)
    structure_key = hash_request(structure_messages, gateway.client().model_id("strong"))
    gateway.replay.register(structure_key, json.dumps(STRUCTURE_CASSETTE))


async def test_scenario1_extraction_and_promotion(client: AsyncClient, auth, app: FastAPI) -> None:
    _register_cassettes()
    pm = await auth("project_manager")

    async with app.state.session_factory() as session:
        source = ApprovedSource(
            type="m365",
            name="M365 demo",
            owner="IT",
            ai_processing_allowed=True,
            enabled=True,
        )
        session.add(source)
        await session.flush()
        artifact = SourceArtifact(
            source_id=source.id,
            kind="meeting_transcript",
            external_id="sc1-001",
            title="Weekly review",
            payload={"body": TEST_TRANSCRIPT},
            content_hash="sc1",
            classification="internal",
            ai_processing_allowed=False,
            language="en",
        )
        session.add(artifact)
        await session.flush()

        # AI analysis (replay): extraction pass → extracted_item suggestion.
        analysis = await run_ai_analysis(session, source)
        assert analysis["suggestions"] >= 1

        suggestion = (
            (
                await session.execute(
                    select(AiSuggestion).where(AiSuggestion.kind == "extracted_item")
                )
            )
            .scalars()
            .first()
        )
        assert suggestion is not None and suggestion.status == "pending"
        assert suggestion.evidence is not None
        assert suggestion.evidence["quote"] == "The pump on line 3 failed during yesterday's shift."

        # Accept via the inbox API → promotion creates the work item.
        response = await client.post(f"/api/v1/ai/suggestions/{suggestion.id}/accept", headers=pm)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "accepted"

        # Fresh sessions: the endpoint commits in its own session.
        async with app.state.session_factory() as fresh:
            accepted = (
                (await fresh.execute(select(AiSuggestion).where(AiSuggestion.id == suggestion.id)))
                .scalars()
                .first()
            )
            assert accepted is not None and accepted.status == "accepted"
            assert accepted.resulting_entity is not None
            item = (
                (
                    await fresh.execute(
                        select(WorkItem).where(WorkItem.id == accepted.resulting_entity)
                    )
                )
                .scalars()
                .first()
            )
            assert item is not None
            assert item.origin == "ai_extracted"
            assert item.title == "Replace pump assembly on line 3"
            assert item.type == "task"

        # derived_from link to the source artifact.
        link = (
            (
                await session.execute(
                    select(WorkLink).where(
                        WorkLink.src_id == item.id, WorkLink.link_type == "derived_from"
                    )
                )
            )
            .scalars()
            .first()
        )
        assert link is not None and link.dst_id == artifact.id

        # llm_call telemetry recorded (replay mode).
        calls = (
            (
                await session.execute(
                    select(__import__("eil.ai.models", fromlist=["LlmCall"]).LlmCall)
                )
            )
            .scalars()
            .all()
        )
        assert len(calls) >= 2
