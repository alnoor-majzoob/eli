"""Prioritisation & scoring (plan §9.1, Phase 5, T5.1-T5.8)."""

from __future__ import annotations

import json
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from test_connectors import _start_sim

from eil.ai.gateway import get_gateway
from eil.ai.gateway.telemetry import hash_request
from eil.ai.pipeline.scoring import create_priority_scores_suggestion, propose_score_assist
from eil.ai.prompts.registry import prompt_registry
from eil.ai.schemas import ScoreAssistOutput
from eil.core.security import Principal
from eil.modules.audit.models import AuditLog
from eil.modules.execution.models import WorkItem, WorkLink, WorkType
from eil.modules.identity.models import User
from eil.modules.identity.rbac import PermissionContext
from eil.modules.integration.models import ApprovedSource, ExternalRef
from eil.modules.prioritization.conversion import convert_demand_to_delivery
from eil.modules.prioritization.models import ScoreOverride
from eil.modules.prioritization.p6 import bind_p6_project, read_project_from_p6
from eil.modules.prioritization.service import (
    _normalise,
    compute_score,
    get_active_model,
    load_criteria,
    tier_from_score,
)


def _ctx() -> PermissionContext:
    principal = Principal(subject="prio-test", name="Prio Test", email="prio-test@eil.test")
    user = User(subject="prio-test", email="prio-test@eil.test", name="Prio Test")
    return PermissionContext(
        principal=principal, user=user, roles=("admin",), scope="global", permission="work.edit"
    )


def test_tier_from_score_defaults() -> None:
    assert tier_from_score(Decimal("75")) == 1
    assert tier_from_score(Decimal("70")) == 2
    assert tier_from_score(Decimal("40")) == 3
    assert tier_from_score(Decimal("10")) == 4


def test_normalise_direction() -> None:
    assert _normalise(5, "benefit") == Decimal("1")
    assert _normalise(1, "benefit") == Decimal("0")
    assert _normalise(1, "cost") == Decimal("1")
    assert _normalise(5, "cost") == Decimal("0")


async def test_compute_score_formula_and_gating(app) -> None:
    async with app.state.session_factory() as session:
        demand = WorkItem(
            type=WorkType.DEMAND,
            title="Flare gas recovery",
            status="active",
            attributes={"scores": {"strategic_alignment": 5}},
        )
        session.add(demand)
        await session.flush()
        score = await compute_score(session, demand)
        await session.commit()
        # Only strategic_alignment differs from the midpoint default (3):
        # score = 100 * (0.20 * 1 + defaults at 0.5) = 60.00 → tier 2.
        assert score.score == Decimal("60.00")
        assert score.tier == 2
        # Gating: HSE-critical floors the tier (plan §9.1).
        demand2 = WorkItem(
            type=WorkType.DEMAND,
            title="Critical recovery",
            status="active",
            hse_critical=True,
            attributes={"scores": {"strategic_alignment": 5}},
        )
        session.add(demand2)
        await session.flush()
        score2 = await compute_score(session, demand2)
        assert score2.tier == 1


async def test_ai_score_assist_creates_suggestion(app) -> None:
    gateway = get_gateway()
    async with app.state.session_factory() as session:
        item = WorkItem(type=WorkType.DEMAND, title="AI-scored demand", status="active")
        session.add(item)
        await session.flush()
        model = await get_active_model(session)
        criteria = await load_criteria(session, model.id)
        criteria_json = json.dumps(
            {
                c.criterion: {
                    "weight": float(c.weight),
                    "direction": c.direction,
                    "anchored_scale": c.anchored_scale,
                }
                for c in criteria
            }
        )
        prompt = prompt_registry.get("score_assist")
        input_data = {
            "item_json": json.dumps({"id": str(item.id), "title": item.title, "description": None}),
            "criteria_json": criteria_json,
            "evidence_json": "[]",
        }
        key = hash_request(prompt.build_messages(input_data), gateway.client().model_id("strong"))
        cassette = ScoreAssistOutput(
            scores=[
                {
                    "criterion": "strategic_alignment",
                    "score": 5,
                    "rationale": "Aligns with the zero-incidents objective.",
                }
            ],
            explanation="Demand directly supports the objective.",
        ).model_dump(mode="json")
        gateway.replay.register(key, json.dumps(cassette))
        proposals = await propose_score_assist(session, item)
        suggestion = await create_priority_scores_suggestion(session, item, proposals)
        await session.commit()
        assert proposals["scores"]["strategic_alignment"] == 5
        assert suggestion.kind == "priority_scores"
        assert suggestion.status == "pending"
        assert suggestion.payload["explanation"] == "Demand directly supports the objective."


async def test_convert_demand_to_delivery(app) -> None:
    async with app.state.session_factory() as session:
        objective = WorkItem(type=WorkType.OBJECTIVE, title="Zero HSSE incidents", status="active")
        session.add(objective)
        await session.flush()
        demand = WorkItem(
            type=WorkType.DEMAND,
            title="Flare gas recovery upgrade",
            status="approved",
            attributes={"scores": {"strategic_alignment": 5}},
        )
        session.add(demand)
        await session.flush()
        session.add(
            WorkLink(
                src_id=demand.id,
                dst_id=objective.id,
                link_type="aligns_to",
                origin="system",
                status="active",
                weight=1,
            )
        )
        await session.flush()
        await compute_score(session, demand)

        project = await convert_demand_to_delivery(session, _ctx(), demand.id)
        await session.commit()

        assert project.type == WorkType.PROJECT
        assert project.title == "Delivery: Flare gas recovery upgrade"
        assert project.status == "draft"
        alignment = (
            (
                await session.execute(
                    select(WorkLink).where(
                        WorkLink.src_id == project.id, WorkLink.link_type == "aligns_to"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert any(link.dst_id == objective.id for link in alignment)
        realizes = (
            (
                await session.execute(
                    select(WorkLink).where(
                        WorkLink.src_id == project.id, WorkLink.link_type == "realizes"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(realizes) == 2
        benefits = [
            item
            for item in (
                (
                    await session.execute(
                        select(WorkItem).where(WorkItem.id.in_([link.dst_id for link in realizes]))
                    )
                )
                .scalars()
                .all()
            )
            if item.type == WorkType.BENEFIT
        ]
        assert len(benefits) == 2


async def test_p6_bind_and_read(app) -> None:
    process = _start_sim("p6_sim", 9101)
    try:
        source = ApprovedSource(type="p6", name="P6 sim", owner="IT")
        async with app.state.session_factory() as session:
            session.add(source)
            await session.flush()
            project = WorkItem(type=WorkType.PROJECT, title="Delivery: P6 Project", status="draft")
            session.add(project)
            await session.flush()

            await bind_p6_project(session, source, project.id, "P6-2026-01")
            count = await read_project_from_p6(session, source, project.id)
            assert count >= 4  # 3 activities + 1 milestone each
            await session.commit()

            # Status sync: A-101 "Complete" → task status completed (ACTIVITY_TO_STATUS).
            task = (
                (
                    await session.execute(
                        select(WorkItem).where(WorkItem.title == "Activate HSSE standards")
                    )
                )
                .scalars()
                .first()
            )
            assert task is not None
            assert task.status == "completed"

            # Milestones created for activities.
            milestones = (
                (await session.execute(select(WorkItem).where(WorkItem.type == WorkType.MILESTONE)))
                .scalars()
                .all()
            )
            assert len(milestones) >= 1
            ref = (
                (await session.execute(select(ExternalRef).where(ExternalRef.system == "p6")))
                .scalars()
                .all()
            )
            assert any(r.external_id == "P6-2026-01" for r in ref)
    finally:
        process.terminate()
        process.wait(timeout=5)


async def test_allocations_api(client: AsyncClient, auth, app) -> None:
    pm = await auth("resource_manager")
    async with app.state.session_factory() as session:
        user = User(subject="prio-alloc", email="prio-alloc@eil.test", name="Prio Alloc")
        session.add(user)
        await session.flush()
        resource_id = user.id

    created = await client.post(
        "/api/v1/allocations",
        json={
            "resource_id": str(resource_id),
            "kind": "project",
            "start_date": "2026-11-01",
            "end_date": "2026-12-31",
            "hours_total": 100,
        },
        headers=pm,
    )
    assert created.status_code == 201, created.text
    allocation_id = created.json()["id"]

    listed = await client.get("/api/v1/allocations", headers=pm)
    assert listed.status_code == 200
    assert any(row["id"] == allocation_id for row in listed.json())

    patched = await client.patch(
        f"/api/v1/allocations/{allocation_id}",
        json={"hours_per_week": 20, "locked": True},
        headers=pm,
    )
    assert patched.status_code == 200
    assert patched.json()["hours_per_week"] == 20


async def test_completed_percent_on_work_item(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    response = await client.post(
        "/api/v1/items", json={"type": "task", "title": "Progress task"}, headers=pm
    )
    assert response.status_code == 201
    item_id = response.json()["id"]

    updated = await client.patch(
        f"/api/v1/items/{item_id}", json={"completed_percent": 45}, headers=pm
    )
    assert updated.status_code == 200, updated.text
    assert float(updated.json()["completed_percent"] or 0) == 45


async def test_prioritization_board_lists_scores(client: AsyncClient, auth, app) -> None:
    pm = await auth("project_manager")
    async with app.state.session_factory() as session:
        demand = WorkItem(
            type=WorkType.DEMAND,
            title="Scored demand",
            status="active",
            attributes={"scores": {"strategic_alignment": 5}},
        )
        session.add(demand)
        await session.flush()
        score = await compute_score(session, demand)
        await session.commit()

    response = await client.get("/api/v1/prioritization", headers=pm)
    assert response.status_code == 200
    rows = response.json()
    row = next((r for r in rows if r["id"] == str(demand.id)), None)
    assert row is not None
    assert row["tier"] == score.tier
    assert row["in_cut_line"] is (score.tier >= 3)


async def test_override_applies_and_preserves_original(client: AsyncClient, auth, app) -> None:
    pm = await auth("portfolio_manager")
    async with app.state.session_factory() as session:
        approver = User(
            subject="prio-approver",
            email="prio-approver@eil.test",
            name="Prio Approver",
        )
        session.add(approver)
        await session.flush()
        demand = WorkItem(
            type=WorkType.DEMAND,
            title="Override target demand",
            status="active",
            attributes={"scores": {"strategic_alignment": 5}},
        )
        session.add(demand)
        await session.flush()
        score = await compute_score(session, demand)
        await session.commit()

    response = await client.post(
        f"/api/v1/prioritization/{demand.id}/override",
        json={
            "tier": 1,
            "justification": "Strategic priority raised",
            "approver_id": str(approver.id),
        },
        headers=pm,
    )
    assert response.status_code == 200, response.text
    override = response.json()
    assert override["tier"] == 1
    assert override["original_tier"] == score.tier
    assert override["justification"] == "Strategic priority raised"
    assert override["approver_id"] == str(approver.id)

    board = await client.get("/api/v1/prioritization", headers=pm)
    row = next(r for r in board.json() if r["id"] == str(demand.id))
    assert row["tier"] == 1

    async with app.state.session_factory() as session:
        audit = (
            (
                await session.execute(
                    select(AuditLog).where(AuditLog.action == "priority.overridden")
                )
            )
            .scalars()
            .all()
        )
        assert any(
            str(a.entity_id) == str(score.id) and a.after and a.after.get("tier") == 1
            for a in audit
        )


async def test_override_rejects_self_approval(client: AsyncClient, auth, app) -> None:
    pm = await auth("portfolio_manager")
    async with app.state.session_factory() as session:
        requester = User(
            subject="demo-portfolio",
            email="demo-portfolio@example.invalid",
            name="Demo Portfolio",
        )
        session.add(requester)
        await session.flush()
        demand = WorkItem(type=WorkType.DEMAND, title="Self-approval target", status="active")
        session.add(demand)
        await session.flush()
        await compute_score(session, demand)
        await session.commit()

    response = await client.post(
        f"/api/v1/prioritization/{demand.id}/override",
        json={
            "tier": 1,
            "justification": "Self approval attempt",
            "approver_id": str(requester.id),
        },
        headers=pm,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "sod_violation"
    async with app.state.session_factory() as session:
        overrides = (await session.execute(select(ScoreOverride))).scalars().all()
        assert overrides == []


async def test_users_endpoint_lists_active_users(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    response = await client.get("/api/v1/users", headers=pm)
    assert response.status_code == 200, response.text
    subjects = [row["subject"] for row in response.json()]
    assert "demo-project" in subjects
    row = next(r for r in response.json() if r["subject"] == "demo-project")
    assert row["name"] and row["roles"]
