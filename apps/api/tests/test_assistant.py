"""Ask EIL assistant (plan Phase 8, T8.3 v1)."""

from __future__ import annotations

import pytest

from eil.core.errors import AppError
from eil.core.security import Principal
from eil.modules.assistant.service import _execute_tool, ask_eil
from eil.modules.execution.models import WorkItem, WorkType
from eil.modules.identity.models import User
from eil.modules.identity.rbac import PermissionContext


def _ctx() -> PermissionContext:
    principal = Principal(subject="assistant-test", name="Assistant", email="assistant@eil.test")
    user = User(subject="assistant-test", email="assistant@eil.test", name="Assistant")
    return PermissionContext(
        principal=principal,
        user=user,
        roles=("project_manager",),
        scope="global",
        permission="work.view",
    )


async def test_assistant_unavailable_when_ai_disabled(app) -> None:
    async with app.state.session_factory() as session:
        with pytest.raises(AppError) as excinfo:
            await ask_eil(session, _ctx(), "What is at risk?")
    assert excinfo.value.status_code == 409
    assert excinfo.value.code == "not_available"


async def test_assistant_endpoint(client, auth) -> None:
    pm = await auth("project_manager")
    response = await client.post(
        "/api/v1/assistant/ask", json={"question": "What is at risk?"}, headers=pm
    )
    assert response.status_code == 409


async def test_execute_tool_get_risks(app) -> None:
    async with app.state.session_factory() as session:
        output = await _execute_tool(session, _ctx(), "get_risks", {})
        assert "at_risk" in output
        assert "interventions" in output


async def test_execute_tool_query_graph(app) -> None:
    async with app.state.session_factory() as session:
        item = WorkItem(type=WorkType.TASK, title="Root task", status="active")
        session.add(item)
        await session.commit()
        output = await _execute_tool(session, _ctx(), "query_graph", {"item_id": str(item.id)})
        assert output["root_id"] == str(item.id)
        assert isinstance(output["items"], list)


async def test_execute_tool_unknown_rejected(app) -> None:
    async with app.state.session_factory() as session:
        with pytest.raises(AppError):
            await _execute_tool(session, _ctx(), "delete_everything", {})
