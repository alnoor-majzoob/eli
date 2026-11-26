"""Assistant conversation logging (plan Phase 8, T8.3).

- ``upsert_conversation`` appends exchanges; conversations are principal-scoped.
- ``list_conversations`` / ``get_conversation`` read models.
- ``ask_eil`` persists a conversation per ask (``conversation_id`` in the payload).
"""

from __future__ import annotations

import pytest

from eil.core.errors import AppError
from eil.core.security import Principal
from eil.modules.assistant import service
from eil.modules.assistant.models import AssistantConversation
from eil.modules.identity.models import User
from eil.modules.identity.rbac import PermissionContext


def _ctx(subject: str) -> PermissionContext:
    principal = Principal(subject=subject, name=subject.title(), email=f"{subject}@eil.test")
    user = User(subject=subject, email=f"{subject}@eil.test", name=subject.title())
    return PermissionContext(
        principal=principal,
        user=user,
        roles=("executive",),
        scope="global",
        permission="work.view",
    )


async def test_upsert_and_list_conversations(app) -> None:
    async with app.state.session_factory() as session:
        conversation = AssistantConversation(
            principal="assistant-conv-a",
            title="First question",
            messages=[{"role": "user", "content": "hi"}],
        )
        session.add(conversation)
        other = AssistantConversation(principal="assistant-conv-b", title="Other", messages=[])
        session.add(other)
        await session.commit()
        conversation_id = conversation.id

    async with app.state.session_factory() as session:
        updated = await service.upsert_conversation(
            session, _ctx("assistant-conv-a"), conversation_id, "second question", "answer"
        )
        assert [message["role"] for message in updated.messages] == ["user", "user", "assistant"]

    async with app.state.session_factory() as session:
        rows = await service.list_conversations(session, _ctx("assistant-conv-a"))
        assert [row.id for row in rows] == [conversation_id]
        detail = await service.get_conversation(session, _ctx("assistant-conv-a"), conversation_id)
        assert detail.messages[-1] == {"role": "assistant", "content": "answer"}


async def test_conversations_are_principal_scoped(app) -> None:
    async with app.state.session_factory() as session:
        conversation = AssistantConversation(principal="assistant-conv-a", title="A", messages=[])
        session.add(conversation)
        await session.commit()
        conversation_id = conversation.id

    async with app.state.session_factory() as session:
        rows = await service.list_conversations(session, _ctx("assistant-conv-b"))
        assert all(row.principal == "assistant-conv-b" for row in rows)
        with pytest.raises(AppError) as excinfo:
            await service.get_conversation(session, _ctx("assistant-conv-b"), conversation_id)
        assert excinfo.value.status_code == 404


async def test_conversation_endpoints(client, auth) -> None:
    headers = await auth("executive")
    response = await client.get("/api/v1/assistant/conversations", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
