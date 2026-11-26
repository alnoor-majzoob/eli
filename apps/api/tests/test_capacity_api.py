"""Capacity API: heatmap, conflicts, optimiser, scenarios (plan §10, Phase 6, T6.7)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from eil.modules.capacity import engine
from eil.modules.capacity.models import ResourceContract
from eil.modules.execution.models import Allocation, WorkItem, WorkLink, WorkType
from eil.modules.identity.models import User


def _week() -> date:
    return engine.week_start(date(2026, 11, 22))


def _mk_user(subject: str) -> User:
    return User(
        subject=subject, email=f"{subject}@eil.test", name=subject.replace("-", " ").title()
    )


async def test_capacity_heatmap_and_conflicts(client, auth, app) -> None:
    week = _week()
    pm = await auth("portfolio_manager")
    async with app.state.session_factory() as session:
        user = _mk_user("cap-api")
        session.add(user)
        await session.flush()
        session.add(
            ResourceContract(
                resource_id=user.id,
                start_date=week,
                end_date=week + timedelta(days=6),
                hours_per_week=Decimal("40"),
                status="active",
            )
        )
        project = WorkItem(type=WorkType.PROJECT, title="Heatmap project", status="active")
        commitment = WorkItem(
            type=WorkType.COMMITMENT,
            title="Heatmap commitment",
            status="active",
            baseline_end=week + timedelta(days=20),
        )
        session.add_all([project, commitment])
        await session.flush()
        session.add(
            WorkLink(
                src_id=project.id,
                dst_id=commitment.id,
                link_type="fulfils",
                origin="system",
                status="active",
                weight=1,
            )
        )
        session.add(
            Allocation(
                resource_id=user.id,
                work_item_id=project.id,
                kind="project",
                start_date=week,
                end_date=week + timedelta(days=6),
                hours_per_week=Decimal("45"),
            )
        )
        await session.commit()
        user_id = str(user.id)
        commitment_id = str(commitment.id)

    heatmap = await client.get("/api/v1/capacity/heatmap", headers=pm)
    assert heatmap.status_code == 200, heatmap.text
    row = next(r for r in heatmap.json()["resources"] if r["resource_id"] == user_id)
    assert row["weeks"]
    assert row["weeks"][0]["status"] == "red"

    conflicts = await client.get("/api/v1/capacity/conflicts", headers=pm)
    assert conflicts.status_code == 200, conflicts.text
    conflict = next((c for c in conflicts.json() if c["resource_id"] == user_id), None)
    assert conflict is not None
    assert conflict["status"] == "red"
    assert any(item["id"] == commitment_id for item in conflict["affected"])


async def test_capacity_optimise_endpoint(client, auth, app) -> None:
    week = _week()
    pm = await auth("portfolio_manager")
    async with app.state.session_factory() as session:
        user = _mk_user("cap-api-opt")
        session.add(user)
        await session.flush()
        session.add(
            ResourceContract(
                resource_id=user.id,
                start_date=week,
                end_date=week + timedelta(days=6),
                hours_per_week=Decimal("40"),
                status="active",
            )
        )
        task = WorkItem(
            type=WorkType.TASK,
            title="Optimise task",
            status="active",
            planned_start=week,
            planned_end=week + timedelta(days=6),
            attributes={"effort_hours": "25"},
        )
        session.add(task)
        await session.commit()

    response = await client.post("/api/v1/capacity/optimise", headers=pm)
    assert response.status_code == 200, response.text
    rows = response.json()
    assert rows
    assert {"strategy", "option_index", "allocations", "deltas"} <= set(rows[0])
    assert sum(row["hours"] for row in rows[0]["allocations"]) == 25


async def test_scenarios_lifecycle(client, auth, app) -> None:
    pm = await auth("portfolio_manager")
    async with app.state.session_factory() as session:
        approver = _mk_user("cap-api-approver")
        session.add(approver)
        await session.commit()
        approver_id = str(approver.id)

    created = await client.post("/api/v1/scenarios", json={"name": "What-if A"}, headers=pm)
    assert created.status_code == 201, created.text
    scenario_id = created.json()["id"]
    assert created.json()["promoted"] is False

    change = await client.post(
        f"/api/v1/scenarios/{scenario_id}/changes",
        json={"payload": {"hours_per_week": "30"}},
        headers=pm,
    )
    assert change.status_code == 200, change.text
    assert change.json()["payload"]["hours_per_week"] == "30"

    promoted = await client.post(
        f"/api/v1/scenarios/{scenario_id}/promote",
        json={"approver_id": approver_id},
        headers=pm,
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["promoted"] is True

    created_b = await client.post("/api/v1/scenarios", json={"name": "What-if B"}, headers=pm)
    second_id = created_b.json()["id"]
    requester = (
        (await session.execute(select(User).where(User.subject == "demo-portfolio")))
        .scalars()
        .first()
    )
    if requester is not None:
        self_deny = await client.post(
            f"/api/v1/scenarios/{second_id}/promote",
            json={"approver_id": str(requester.id)},
            headers=pm,
        )
        assert self_deny.status_code == 403

    metrics = await client.get(f"/api/v1/scenarios/{scenario_id}/metrics", headers=pm)
    assert metrics.status_code == 200, metrics.text
    assert set(metrics.json()) >= {
        "overload_hours",
        "red_weeks",
        "delayed_commitments",
        "cost_proxy",
    }

    listed = await client.get("/api/v1/scenarios", headers=pm)
    assert listed.status_code == 200
    assert any(row["id"] == scenario_id for row in listed.json())
