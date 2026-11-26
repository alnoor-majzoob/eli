"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from eil.core.config import Settings
from eil.core.db import Base
from eil.core.security import Principal, create_dev_token
from eil.main import create_app
from eil.modules.audit.guards import install_audit_guards
from eil.modules.identity.models import OrgUnit, User
from eil.modules.seed import seed_reference_data

AuthHeaders = Callable[[str], Awaitable[dict[str, str]]]
MakeToken = Callable[..., dict[str, str]]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="local",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        auth_mode="dev",
        outbox_inline_dispatcher=False,
        metrics_enabled=True,
        log_level="WARNING",
        log_format="console",
        object_store_local_dir=tmp_path / "objects",
    )


@pytest_asyncio.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(settings)
    async with LifespanManager(application):
        engine: AsyncEngine = application.state.engine
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await install_audit_guards(engine)
        async with application.state.session_factory() as session:
            await seed_reference_data(session)
        yield application
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture
def make_token(settings: Settings) -> MakeToken:
    def _make(
        subject: str,
        roles: list[str],
        org_unit_id: str | None = "pmo",
        name: str | None = None,
        email: str | None = None,
    ) -> dict[str, str]:
        principal = Principal(
            subject=subject,
            name=name or subject.replace("-", " ").title(),
            email=email or f"{subject}@example.invalid",
            roles=roles,
            org_unit_id=org_unit_id,
        )
        token = create_dev_token(principal, settings).access_token
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest_asyncio.fixture
async def user_id(app: FastAPI):
    async def _lookup(subject: str):
        async with app.state.session_factory() as session:
            return (
                await session.execute(select(User.id).where(User.subject == subject))
            ).scalar_one()

    return _lookup


@pytest_asyncio.fixture
async def org_id(app: FastAPI):
    async def _lookup(code: str):
        async with app.state.session_factory() as session:
            return (
                await session.execute(select(OrgUnit.id).where(OrgUnit.code == code))
            ).scalar_one()

    return _lookup


@pytest_asyncio.fixture
async def auth(client: AsyncClient) -> AsyncIterator[AuthHeaders]:
    tokens: dict[str, str] = {}

    async def headers_for(role: str) -> dict[str, str]:
        if role not in tokens:
            response = await client.post("/api/v1/auth/dev-login", json={"role": role})
            assert response.status_code == 200, response.text
            tokens[role] = response.json()["access_token"]
        return {"Authorization": f"Bearer {tokens[role]}"}

    yield headers_for
