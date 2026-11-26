"""Outbox behaviour: persistence, dispatch, retry/dead-letter."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from eil.core.events import clear_handlers, register_handler
from eil.core.outbox import OutboxEvent, dispatch_pending, emit


@pytest.fixture(autouse=True)
def _clean_handlers():
    clear_handlers()
    yield
    clear_handlers()


async def test_emit_and_dispatch(app: FastAPI) -> None:
    received: list[dict[str, object]] = []

    async def handler(event: OutboxEvent) -> None:
        received.append(event.payload)

    register_handler("work.created", handler)

    factory = app.state.session_factory
    async with factory() as session:
        await emit(session, "work.created", {"id": "w-1"})
        await session.commit()

    async with factory() as session:
        processed = await dispatch_pending(session)
    assert processed == 1
    assert received == [{"id": "w-1"}]

    async with factory() as session:
        row = (await session.execute(select(OutboxEvent))).scalar_one()
        assert row.processed_at is not None
        assert row.attempts == 0


async def test_failed_handler_retries_then_dead_letters(app: FastAPI) -> None:
    async def handler(event: OutboxEvent) -> None:
        raise RuntimeError("handler boom")

    register_handler("work.failed", handler)

    factory = app.state.session_factory
    async with factory() as session:
        await emit(session, "work.failed", {})
        await session.commit()

    for _ in range(5):
        async with factory() as session:
            await dispatch_pending(session)

    async with factory() as session:
        row = (await session.execute(select(OutboxEvent))).scalar_one()
        assert row.attempts == 5
        assert row.processed_at is not None
        assert "handler boom" in (row.last_error or "")


async def test_no_handler_is_marked_processed(app: FastAPI) -> None:
    factory = app.state.session_factory
    async with factory() as session:
        await emit(session, "nobody.listens", {"a": 1})
        await session.commit()

    async with factory() as session:
        processed = await dispatch_pending(session)
    assert processed == 1
