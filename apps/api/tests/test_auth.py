"""Authentication and authorisation tests (dev auth path)."""

from __future__ import annotations

from httpx import AsyncClient


async def test_auth_config_exposes_demo_roles(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/config")
    assert response.status_code == 200
    body = response.json()
    assert body["auth_mode"] == "dev"
    assert body["dev_login_enabled"] is True
    roles = {role["role"] for role in body["roles"]}
    assert {"executive", "project_manager", "auditor", "admin"} <= roles


async def test_me_requires_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "unauthenticated"
    assert body["status"] == 401
    assert body["request_id"]


async def test_dev_login_and_me(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/dev-login", json={"role": "project_manager"})
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert response.json()["principal"]["roles"] == ["project_manager"]

    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["subject"] == "demo-project"
    assert body["roles"] == ["project_manager"]
    assert body["org_unit_id"] == "projects"


async def test_unknown_dev_role(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/dev-login", json={"role": "wizard"})
    assert response.status_code == 400
    assert response.json()["code"] == "unknown_role"
    assert "available_roles" in response.json()


async def test_invalid_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


async def test_dev_login_disabled_in_prod(settings) -> None:
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from eil.main import create_app

    prod_settings = settings.model_copy(update={"app_env": "prod", "auth_mode": "oidc"})
    application = create_app(prod_settings)
    async with LifespanManager(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/auth/dev-login", json={"role": "admin"})
            assert response.status_code == 404
            assert response.json()["code"] == "not_found"
