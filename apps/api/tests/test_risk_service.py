"""Predictive execution service (plan §9.5, Phase 7, T7.4-T7.6)."""

from __future__ import annotations

from decimal import Decimal

from eil.core.security import Principal
from eil.modules.execution.models import WorkItem, WorkLink, WorkType
from eil.modules.identity.models import User
from eil.modules.identity.rbac import PermissionContext
from eil.modules.risk import service


def _ctx() -> PermissionContext:
    principal = Principal(subject="risk-svc", name="Risk Svc", email="risk-svc@eil.test")
    user = User(subject="risk-svc", email="risk-svc@eil.test", name="Risk Svc")
    return PermissionContext(
        principal=principal, user=user, roles=("admin",), scope="global", permission="work.view"
    )


async def test_rollup_confidence_heuristic(app) -> None:
    async with app.state.session_factory() as session:
        project = WorkItem(type=WorkType.PROJECT, title="Rollup project", status="active")
        commitment_a = WorkItem(
            type=WorkType.COMMITMENT,
            title="Critical",
            status="active",
            delivery_confidence=Decimal("0.30"),
        )
        commitment_b = WorkItem(
            type=WorkType.COMMITMENT,
            title="On track",
            status="active",
            delivery_confidence=Decimal("0.90"),
        )
        session.add_all([project, commitment_a, commitment_b])
        await session.flush()
        session.add(
            WorkLink(
                src_id=project.id,
                dst_id=commitment_a.id,
                link_type="fulfils",
                origin="system",
                status="active",
                weight=1,
            )
        )
        session.add(
            WorkLink(
                src_id=project.id,
                dst_id=commitment_b.id,
                link_type="fulfils",
                origin="system",
                status="active",
                weight=1,
            )
        )
        await session.commit()

        written = await service.rollup_confidence(session, _ctx())

        assert project.id in written
        # 0.6 x 0.30 + 0.4 x weighted_mean([0.30, 0.90]) = 0.18 + 0.4 x 0.6 = 0.42
        assert written[project.id] == Decimal("0.42")


async def test_generate_escalations_esc1(app) -> None:
    async with app.state.session_factory() as session:
        commitment = WorkItem(
            type=WorkType.COMMITMENT,
            title="Low confidence",
            status="active",
            delivery_confidence=Decimal("0.20"),
        )
        session.add(commitment)
        await session.commit()

        created = await service.generate_escalations(session)

        assert any(
            row.target_role == "dept_head"
            and row.work_item_id == commitment.id
            and row.status == "open"
            for row in created
        )
