"""The OpenAPI contract contains the Phase 0 surface and security scheme."""

from __future__ import annotations

from fastapi import FastAPI


def test_openapi_surface(app: FastAPI) -> None:
    spec = app.openapi()
    paths = spec["paths"]
    assert "/healthz" in paths
    assert "/readyz" in paths
    assert "/api/v1/me" in paths
    assert "/api/v1/auth/dev-login" in paths
    assert spec["info"]["title"].startswith("EIL")
    assert "HTTPBearer" in spec["components"]["securitySchemes"]
    me = paths["/api/v1/me"]["get"]
    assert me["security"]
