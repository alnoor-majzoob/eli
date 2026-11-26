"""RFC 7807 error rendering tests."""

from __future__ import annotations

from httpx import AsyncClient


async def test_not_found_is_problem_json(client: AsyncClient) -> None:
    response = await client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["type"].endswith("/not_found")
    assert body["title"] == "Not found"
    assert body["instance"] == "/does-not-exist"
    assert body["request_id"]


async def test_validation_error_is_problem_json(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/dev-login",
        content=b"{not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["errors"]


async def test_request_id_header_matches_body(client: AsyncClient) -> None:
    response = await client.get("/does-not-exist", headers={"X-Request-ID": "trace-42"})
    assert response.headers["x-request-id"] == "trace-42"
    assert response.json()["request_id"] == "trace-42"
