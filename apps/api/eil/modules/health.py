"""Platform health and readiness endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

router = APIRouter(tags=["platform"])


@router.get("/healthz")
async def healthz(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "env": settings.app_env,
    }


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    factory = request.app.state.session_factory
    dependencies: dict[str, str] = {}
    healthy = True

    try:
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        dependencies["database"] = "up"
    except Exception as exc:
        dependencies["database"] = f"down: {type(exc).__name__}"
        healthy = False

    settings = request.app.state.settings
    dependencies["redis"] = "configured" if settings.redis_url else "not_configured"
    dependencies["object_store"] = settings.object_store_backend

    payload = {
        "status": "ok" if healthy else "unavailable",
        "dependencies": dependencies,
    }
    return JSONResponse(status_code=200 if healthy else 503, content=payload)
