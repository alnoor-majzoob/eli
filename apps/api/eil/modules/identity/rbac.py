"""RBAC/ABAC permission resolution and JIT identity provisioning."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypeVar
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.errors import AppError
from eil.core.security import CurrentPrincipal, Principal
from eil.modules.identity.demo_users import DEMO_USERS_BY_ROLE
from eil.modules.identity.models import OrgUnit, RolePermission, User

Permission = str
PermissionScope = Literal["global", "own_org", "none"]
T = TypeVar("T")

# Roles that write or administer data. SOD-5 forbids combining any of these with
# the read-only auditor role.
_WRITE_ROLES = {
    "executive",
    "portfolio_manager",
    "project_manager",
    "dept_head",
    "resource_manager",
    "team_member",
    "pmo_analyst",
    "ai_reviewer",
    "integration_admin",
    "admin",
}


@dataclass(frozen=True)
class PermissionContext:
    principal: Principal
    user: User
    roles: tuple[str, ...]
    scope: PermissionScope
    permission: Permission

    @property
    def org_unit_id(self) -> UUID | None:
        return self.user.org_unit_id

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles

    def can_access_org(self, org_unit_id: UUID | None) -> bool:
        if self.scope == "global":
            return True
        if self.scope == "none":
            return False
        return org_unit_id is not None and org_unit_id == self.user.org_unit_id


async def _get_or_create_org_unit(session: AsyncSession, code: str, name: str) -> OrgUnit:
    """Race-safe org-unit lookup/create (user-test finding).

    Concurrent requests can both pass the select-then-insert check before
    either commits; on the ``IntegrityError`` the concurrently created row is
    re-selected instead of failing the request.
    """
    result = await session.execute(select(OrgUnit).where(OrgUnit.code == code))
    org_unit = result.scalar_one_or_none()
    if org_unit is not None:
        return org_unit
    org_unit = OrgUnit(code=code, name=name)
    session.add(org_unit)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        result = await session.execute(select(OrgUnit).where(OrgUnit.code == code))
        org_unit = result.scalar_one()
        session.add(org_unit)
    return org_unit


async def ensure_user(session: AsyncSession, principal: CurrentPrincipal) -> User:
    """JIT-provision an authenticated identity and map the OIDC org-unit code.

    Race-safe (user-test finding): concurrent requests may both pass the
    select-then-insert checks before either commits; on ``IntegrityError`` the
    concurrently created row is re-selected instead of failing the request.
    """
    result = await session.execute(select(User).where(User.subject == principal.subject))
    user = result.scalar_one_or_none()

    org_unit_id = None
    if principal.org_unit_id:
        demo = next(
            (
                candidate
                for candidate in DEMO_USERS_BY_ROLE.values()
                if candidate.org_unit_id == principal.org_unit_id
            ),
            None,
        )
        display = demo.name if demo else principal.name.title()
        org_unit = await _get_or_create_org_unit(session, principal.org_unit_id, display)
        org_unit_id = org_unit.id

    if user is None:
        user = User(
            subject=principal.subject,
            email=principal.email,
            name=principal.name,
            roles=list(principal.roles),
            org_unit_id=org_unit_id,
            is_active=True,
        )
        session.add(user)
        try:
            await session.flush()
        except IntegrityError:
            # Concurrent creation — reload the existing row and update below.
            await session.rollback()
            user = (
                await session.execute(select(User).where(User.subject == principal.subject))
            ).scalar_one()
            session.add(user)

    # The identity provider is authoritative for roles; never accumulate
    # stale roles from a previous demo login.
    user.roles = list(principal.roles)
    user.name = principal.name
    if principal.email:
        user.email = principal.email
    if org_unit_id is not None:
        user.org_unit_id = org_unit_id
    user.is_active = True

    await session.commit()
    return user


async def resolve_permission_scope(
    session: AsyncSession, roles: Sequence[str], permission: Permission
) -> PermissionScope:
    if not roles:
        return "none"
    if "admin" in roles:
        return "global"

    result = await session.execute(
        select(RolePermission.scope).where(
            RolePermission.role.in_(roles),
            RolePermission.permission == permission,
        )
    )
    scopes = {row[0] for row in result.all()}
    if scopes & {"global"}:
        return "global"
    if scopes & {"own_org"}:
        return "own_org"
    return "none"


async def has_permission(
    session: AsyncSession, roles: Sequence[str], permission: Permission
) -> bool:
    return await resolve_permission_scope(session, roles, permission) != "none"


def check_role_combination(roles: Sequence[str]) -> None:
    if "auditor" in roles and any(role in _WRITE_ROLES for role in roles):
        raise AppError(
            409,
            "sod_violation",
            "Segregation of duties violation",
            "Auditor is read-only and cannot be combined with any write role (SOD-5).",
            extra={"rule": "SOD-5", "roles": list(roles)},
        )


async def _require_permission(
    permission: Permission,
    principal: CurrentPrincipal,
    request: Request,
) -> PermissionContext:
    check_role_combination(principal.roles)
    async with request.app.state.session_factory() as session:
        scope = await resolve_permission_scope(session, principal.roles, permission)
        if scope == "none":
            raise AppError(
                403,
                "forbidden",
                "Insufficient permissions",
                f"Missing permission '{permission}' for your role(s).",
                extra={"permission": permission},
            )
        user = await ensure_user(session, principal)
        request.state.permission_user = user
        return PermissionContext(
            principal=principal,
            user=user,
            roles=tuple(principal.roles),
            scope=scope,
            permission=permission,
        )


def require_permission(permission: Permission) -> Any:
    """FastAPI dependency factory: ``ctx = Depends(require_permission(perms.WORK_VIEW))``."""

    async def dependency(
        principal: CurrentPrincipal,
        request: Request,
    ) -> PermissionContext:
        return await _require_permission(permission, principal, request)

    return dependency


def require_any_permission(*permissions: Permission) -> Any:
    """Allow access when the caller has at least one of the permissions."""

    async def dependency(
        principal: CurrentPrincipal,
        request: Request,
    ) -> PermissionContext:
        check_role_combination(principal.roles)
        async with request.app.state.session_factory() as session:
            for permission in permissions:
                scope = await resolve_permission_scope(session, principal.roles, permission)
                if scope != "none":
                    user = await ensure_user(session, principal)
                    request.state.permission_user = user
                    return PermissionContext(
                        principal=principal,
                        user=user,
                        roles=tuple(principal.roles),
                        scope=scope,
                        permission=permission,
                    )
        raise AppError(
            403,
            "forbidden",
            "Insufficient permissions",
            "Missing one of: " + ", ".join(sorted(permissions)) + ".",
            extra={"permissions": list(permissions)},
        )

    return dependency
