"""Executive metrics layer (plan Phase 8, T8.1, T8.5)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from eil.core.models import utcnow
from eil.core.security import Principal
from eil.modules.execution.models import WorkItem, WorkType
from eil.modules.identity.models import User
from eil.modules.identity.rbac import PermissionContext
from eil.modules.metrics import service


def _ctx() -> PermissionContext:
    principal = Principal(subject="metrics", name="Metrics", email="metrics@eil.test")
    user = User(subject="metrics", email="metrics@eil.test", name="Metrics")
    return PermissionContext(
        principal=principal,
        user=user,
        roles=("admin",),
        scope="global",
        permission="dashboard.view",
    )


async def test_executive_summary(app) -> None:
    async with app.state.session_factory() as session:
        commitment = WorkItem(
            type=WorkType.COMMITMENT,
            title="Commitment",
            status="active",
            delivery_confidence=Decimal("0.7"),
        )
        session.add(commitment)
        await session.flush()
        priority = WorkItem(
            type=WorkType.DEMAND,
            title="Top demand",
            status="active",
            delivery_confidence=Decimal("0.9"),
        )
        session.add(priority)
        await session.commit()

        summary = await service.executive_summary(session, _ctx())

    assert summary["as_of"] is not None
    assert summary["committed"]["total"] >= 1
    assert summary["priorities"][0]["title"] == "Top demand"
    assert summary["priorities"][0]["confidence"] == 0.9
    assert isinstance(summary["strategic_outcomes"]["benefits_total"], int)
    assert isinstance(summary["at_risk"], list)
    assert isinstance(summary["interventions"], list)
    assert isinstance(summary["capacity_constraints"], list)


async def test_executive_summary_as_of_replays_timeline(app) -> None:
    async with app.state.session_factory() as session:
        session.add(WorkItem(type=WorkType.COMMITMENT, title="Commitment recent", status="active"))
        old = WorkItem(type=WorkType.COMMITMENT, title="Commitment old", status="active")
        session.add(old)
        await session.flush()
        old.updated_at = utcnow() - timedelta(days=10)
        await session.commit()

        summary_now = await service.executive_summary(session, _ctx())
        summary_past = await service.executive_summary(
            session, _ctx(), as_of=utcnow() - timedelta(days=5)
        )

    assert summary_now["committed"]["total"] >= 2
    # "Commitment old" was updated 10 days ago: excluded from the past view.
    assert summary_past["committed"]["total"] == summary_now["committed"]["total"] - 1
    assert summary_past["as_of"] is not None
