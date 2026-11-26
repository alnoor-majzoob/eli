"""Public, non-sensitive platform configuration for UI badges (rule R8)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["platform"])


class PlatformConfig(BaseModel):
    app_name: str
    app_version: str
    app_env: str
    auth_mode: str
    ai_enabled: bool
    llm_mode: str
    database: str
    object_store: str
    simulated_systems: list[str]
    tenant_timezone: str
    default_locale: str


@router.get("/platform/config", response_model=PlatformConfig)
async def platform_config(request: Request) -> PlatformConfig:
    settings = request.app.state.settings
    return PlatformConfig(
        app_name=settings.app_name,
        app_version=settings.app_version,
        app_env=settings.app_env,
        auth_mode=settings.auth_mode,
        ai_enabled=settings.ai_enabled,
        llm_mode=settings.llm_mode,
        database="postgresql" if settings.is_postgres else "sqlite",
        object_store=settings.object_store_backend,
        simulated_systems=settings.simulated_systems,
        tenant_timezone=settings.tenant_timezone,
        default_locale=settings.default_locale,
    )
