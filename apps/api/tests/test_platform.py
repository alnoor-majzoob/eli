"""Public platform configuration endpoint (badges, environment banner)."""

from __future__ import annotations

from httpx import AsyncClient


async def test_platform_config(client: AsyncClient) -> None:
    response = await client.get("/api/v1/platform/config")
    assert response.status_code == 200
    body = response.json()
    assert body["app_env"] == "local"
    assert body["auth_mode"] == "dev"
    assert body["database"] == "sqlite"
    assert body["object_store"] == "local"
    assert body["ai_enabled"] is False
    assert body["llm_mode"] == "replay"
    assert set(body["simulated_systems"]) == {"m365", "p6", "eam", "erp", "hr"}
