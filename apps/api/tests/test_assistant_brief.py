"""Executive brief (plan Phase 8, T8.4)."""

from __future__ import annotations

from decimal import Decimal

from eil.core.security import Principal
from eil.modules.assistant import brief
from eil.modules.execution.models import WorkItem, WorkType
from eil.modules.identity.models import User
from eil.modules.identity.rbac import PermissionContext


def _ctx() -> PermissionContext:
    principal = Principal(subject="brief-test", name="Brief", email="brief@eil.test")
    user = User(subject="brief-test", email="brief@eil.test", name="Brief")
    return PermissionContext(
        principal=principal,
        user=user,
        roles=("executive",),
        scope="global",
        permission="dashboard.view",
    )


async def test_executive_brief(app) -> None:
    async with app.state.session_factory() as session:
        session.add(
            WorkItem(
                type=WorkType.COMMITMENT,
                title="Brief commitment",
                status="active",
                delivery_confidence=Decimal("0.8"),
            )
        )
        await session.commit()
        result = await brief.executive_brief(session, _ctx())

    assert "Executive Brief" in result["html"]
    assert result["fact_sheet"]["committed_total"] >= 1
    assert isinstance(result["text"], str | type(None))


async def test_executive_brief_endpoint(client, auth, app) -> None:
    headers = await auth("executive")
    async with app.state.session_factory() as session:
        session.add(
            WorkItem(
                type=WorkType.COMMITMENT,
                title="Endpoint commitment",
                status="active",
                delivery_confidence=Decimal("0.7"),
            )
        )
        await session.commit()

    response = await client.get("/api/v1/executive/brief", headers=headers)

    assert response.status_code == 200, response.text
    data = response.json()
    assert "Executive Brief" in data["html"]
    assert data["fact_sheet"]["committed_total"] >= 1
