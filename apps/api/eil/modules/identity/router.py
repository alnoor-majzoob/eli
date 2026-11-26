"""Identity endpoints: dev login, configuration, the current user and active users."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.db import get_db
from eil.core.errors import AppError
from eil.core.security import (
    CurrentPrincipal,
    DevTokenResponse,
    Principal,
    create_dev_token,
)
from eil.modules.identity.demo_users import DEMO_USERS_BY_ROLE, public_roles
from eil.modules.identity.models import User
from eil.modules.identity.rbac import PermissionContext, require_permission
from eil.modules.seed_data import WORK_VIEW

router = APIRouter(tags=["identity"])

CtxUsers = Annotated[PermissionContext, Depends(require_permission(WORK_VIEW))]
Db = Annotated[AsyncSession, Depends(get_db)]


class DevLoginRequest(BaseModel):
    role: str = "executive"


class AuthConfigResponse(BaseModel):
    auth_mode: str
    dev_login_enabled: bool
    roles: list[dict[str, str]]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subject: str
    name: str
    email: str
    org_unit_id: UUID | None
    roles: list[str]


@router.get("/auth/config", response_model=AuthConfigResponse)
async def auth_config(request: Request) -> AuthConfigResponse:
    settings = request.app.state.settings
    return AuthConfigResponse(
        auth_mode=settings.auth_mode,
        dev_login_enabled=settings.dev_auth_enabled,
        roles=public_roles() if settings.dev_auth_enabled else [],
    )


@router.post("/auth/dev-login", response_model=DevTokenResponse)
async def dev_login(body: DevLoginRequest, request: Request) -> DevTokenResponse:
    """Local/demo only. Disabled whenever AUTH_MODE=oidc or APP_ENV=prod."""
    settings = request.app.state.settings
    if not settings.dev_auth_enabled:
        raise AppError(
            404,
            "not_found",
            "Not found",
            "Dev login is disabled in this environment.",
        )
    user = DEMO_USERS_BY_ROLE.get(body.role)
    if user is None:
        raise AppError(
            400,
            "unknown_role",
            "Unknown role",
            f"Role '{body.role}' is not a configured demo role.",
            extra={"available_roles": sorted(DEMO_USERS_BY_ROLE)},
        )
    return create_dev_token(user.to_principal(), settings)


@router.get("/users", response_model=list[UserRead])
async def list_users(ctx: CtxUsers, session: Db) -> list[UserRead]:
    """List active users (resource directory used by e.g. override approvers)."""
    rows = (
        (
            await session.execute(
                select(User).where(User.is_active.is_(True)).order_by(User.name, User.subject)
            )
        )
        .scalars()
        .all()
    )
    return [UserRead.model_validate(row) for row in rows]


@router.get("/me", response_model=Principal)
async def me(principal: CurrentPrincipal) -> Principal:
    return principal
