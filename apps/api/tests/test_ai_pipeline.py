"""AI pipeline (plan §8.7): artifacts, evidence guard, extraction, owner, classification,
link proposals, promotion, feedback."""

from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select

from eil.ai.gateway import Gateway, get_gateway
from eil.ai.gateway.telemetry import hash_request
from eil.ai.models import AiSuggestion
from eil.ai.pipeline.artifacts import dequote_email, parse_vtt, section_document
from eil.ai.pipeline.classification import create_classification_suggestions
from eil.ai.pipeline.dates import parse_due_text
from eil.ai.pipeline.evidence import verify_evidence
from eil.ai.pipeline.extraction import create_extraction_suggestions
from eil.ai.pipeline.feedback import record_feedback, weekly_feedback_metrics
from eil.ai.pipeline.links import propose_links
from eil.ai.pipeline.owner import load_users, resolve_owner
from eil.ai.pipeline.promotion import accept_suggestion
from eil.ai.prompts.registry import prompt_registry
from eil.ai.schemas import (
    ClassificationOutput,
    OwnerCandidate,
    StructuredItem,
)
from eil.core.security import Principal
from eil.modules.execution.models import WorkItem, WorkLink
from eil.modules.identity.models import User
from eil.modules.identity.rbac import PermissionContext
from eil.modules.integration.models import ApprovedSource, SourceArtifact

TEST_TRANSCRIPT = """1:00:00.000 --> 1:00:03.000
Aisha: The pump on line 3 failed during yesterday's shift.
1:00:03.500 --> 1:00:06.000
Mariam: We need to replace the assembly by Friday.
"""


def _ctx() -> PermissionContext:
    principal = Principal(subject="ai-test", name="AI Test", email="ai-test@eil.test")
    user = User(subject="ai-test", email="ai-test@eil.test", name="AI Test")
    return PermissionContext(
        principal=principal, user=user, roles=("admin",), scope="global", permission="ai.review"
    )


async def _add_source(session, **overrides):
    source = ApprovedSource(
        type="m365",
        name="M365 demo",
        owner="IT",
        ai_processing_allowed=True,
        enabled=True,
        **overrides,
    )
    session.add(source)
    await session.flush()
    return source


async def _add_artifact(session, source, payload=None, **overrides):
    artifact = SourceArtifact(
        source_id=source.id,
        kind="meeting_transcript",
        external_id="artifact-1",
        title="Weekly",
        payload=payload or {"body": TEST_TRANSCRIPT},
        content_hash="abc123",
        classification="internal",
        ai_processing_allowed=False,
        language="en",
        **overrides,
    )
    session.add(artifact)
    await session.flush()
    return artifact


def test_parse_vtt_extracts_speakers() -> None:
    turns = parse_vtt(TEST_TRANSCRIPT)
    assert [turn.speaker for turn in turns] == ["Aisha", "Mariam"]
    assert turns[0].text == "The pump on line 3 failed during yesterday's shift."


def test_dequote_email_strips_quotes() -> None:
    text = "New message\n> quoted line 1\n> quoted line 2\nActual text"
    assert dequote_email(text) == "New message\nActual text"


def test_section_document() -> None:
    sections = section_document("# Heading\ncontent\n## Sub\nmore")
    assert [section.title for section in sections] == ["Heading", "Sub"]


def test_verify_evidence_guard() -> None:
    source = "The pump failed during yesterday's shift. The replacement is due Friday."
    assert verify_evidence(source, "The pump failed during yesterday's shift.")
    assert not verify_evidence(source, "The governor of Alaska visited Mars.")
    assert not verify_evidence(source, "")


def test_parse_due_text() -> None:
    anchor = date(2026, 11, 21)
    assert parse_due_text("2026-11-30", anchor) == (date(2026, 11, 30), False)
    assert parse_due_text("in 3 days", anchor) == (date(2026, 11, 24), False)
    assert parse_due_text("tomorrow-ish", anchor) == (None, True)


async def test_create_extraction_suggestions_with_evidence(app) -> None:
    """Evidence guard: unverified quotes are dropped, verified ones become suggestions."""
    async with app.state.session_factory() as session:
        source = await _add_source(session)
        artifact = await _add_artifact(session, source)
        items = [
            StructuredItem(
                title="Replace pump assembly",
                summary="s",
                kind="task",
                evidence_quote="The pump on line 3 failed during yesterday's shift.",
                priority=1,
            ),
            StructuredItem(
                title="Governor of Alaska",
                summary="s",
                kind="task",
                evidence_quote="The governor of Alaska visited Mars.",
            ),
        ]
        prompt = prompt_registry.get("structure_items")
        suggestions = await create_extraction_suggestions(session, artifact, items, prompt)
        await session.commit()

        assert len(suggestions) == 1
        assert suggestions[0].payload["title"] == "Replace pump assembly"
        assert suggestions[0].status == "pending"
        assert suggestions[0].kind == "extracted_item"


async def test_resolve_owner(app) -> None:
    async with app.state.session_factory() as session:
        for subject, name in [("u1", "Aisha Al-Zadjali"), ("u2", "Mariam Al-Habsi")]:
            session.add(User(subject=subject, email=f"{subject}@eil.test", name=name, roles=[]))
        await session.flush()
        users = await load_users(session)
        candidates = [
            OwnerCandidate(user_id="u1", name="Aisha Al-Zadjali", reason="assignee", score=1.0)
        ]
        owner = resolve_owner(candidates, users)
        assert owner is not None and owner.user_id == "u1"
        assert resolve_owner([], users) is None


async def test_create_classification_suggestions(app) -> None:
    async with app.state.session_factory() as session:
        item = WorkItem(type="task", title="Pump replacement", description="Replace the pump")
        session.add(item)
        await session.flush()
        classifications = [
            ClassificationOutput(
                type="task",
                category="engineering",
                department="maintenance",
                hse_critical=False,
                regulatory=False,
                confidence=0.9,
                reasons=[],
            )
        ]
        suggestions = await create_classification_suggestions(
            session, [{"id": str(item.id)}], classifications
        )
        await session.commit()
        assert len(suggestions) == 1
        assert suggestions[0].kind == "classification"
        assert suggestions[0].status == "pending"


async def test_propose_links_with_replay_cassette(app) -> None:
    gateway: Gateway = get_gateway()
    async with app.state.session_factory() as session:
        objective = WorkItem(type="objective", title="Zero HSSE incidents")
        item = WorkItem(type="task", title="Replace pump assembly", description="s")
        session.add(objective)
        session.add(item)
        await session.flush()

        prompt = prompt_registry.get("rerank_links")
        entities = [{"id": str(objective.id), "title": objective.title, "type": "objective"}]
        item_text = f"{item.title}: {item.description or item.title}"
        messages = prompt.build_messages(
            {"artifact_text": item_text, "entities_json": json.dumps(entities)}
        )
        key = hash_request(messages, gateway.client().model_id("strong"))
        gateway.replay.register(
            key,
            json.dumps(
                {
                    "links": [
                        {
                            "entity_id": str(objective.id),
                            "link_type": "aligns_to",
                            "rationale": "Pump work supports the safety objective",
                            "confidence": 0.9,
                        }
                    ]
                }
            ),
        )
        links = await propose_links(gateway, session, item)
        assert len(links) == 1
        assert links[0].link_type == "aligns_to"
        assert links[0].dst_id == objective.id
        assert links[0].status == "proposed"


async def test_accept_extracted_suggestion_creates_item(app) -> None:
    async with app.state.session_factory() as session:
        source = await _add_source(session)
        artifact = await _add_artifact(session, source)
        items = [
            StructuredItem(
                title="Replace pump assembly",
                summary="Replace the failed pump assembly",
                kind="task",
                evidence_quote="The pump on line 3 failed during yesterday's shift.",
            )
        ]
        prompt = prompt_registry.get("structure_items")
        suggestions = await create_extraction_suggestions(session, artifact, items, prompt)
        assert len(suggestions) == 1
        suggestion = suggestions[0]

        accepted = await accept_suggestion(session, _ctx(), suggestion.id)
        assert accepted.status == "accepted"
        assert accepted.resulting_entity is not None

        item = await session.get(WorkItem, accepted.resulting_entity)
        assert item is not None
        assert item.type == "task"
        assert item.origin == "ai_extracted"
        assert item.title == "Replace pump assembly"

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


async def test_record_feedback_and_weekly_metrics(app) -> None:
    async with app.state.session_factory() as session:
        for kind in ("extracted_item", "extracted_item", "owner"):
            session.add(
                AiSuggestion(
                    kind=kind,
                    payload={},
                    model="ai",
                    prompt_version="test@v1",
                    status="pending",
                )
            )
        await session.flush()
        suggestions = (
            (await session.execute(select(AiSuggestion).order_by(AiSuggestion.created_at)))
            .scalars()
            .all()
        )
        first = suggestions[0]
        await record_feedback(session, first.id, "accepted")
        metrics = await weekly_feedback_metrics(session)
        assert metrics["extracted_item:pending"] == 1
        assert metrics["extracted_item:accepted"] == 1
        assert metrics["owner:pending"] == 1
