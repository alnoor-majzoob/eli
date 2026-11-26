"""Idempotent Phase 1 reference-data seeding (permissions, SoD, workflows, org units)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.modules.execution.models import WorkItem  # noqa: F401
from eil.modules.governance.models import Approval, SoDRule, WorkflowDefinition  # noqa: F401
from eil.modules.identity.models import OrgUnit, RolePermission
from eil.modules.seed_data import (
    ORG_UNITS,
    ROLE_PERMISSIONS,
    WORKFLOW_DEFINITIONS,
)

_SOD_RULES: tuple[dict[str, Any], ...] = (
    {
        "code": "SOD-1",
        "name": "Cannot approve what you created",
        "description": (
            "A user cannot approve a demand, stage gate or change request "
            "they created or submitted."
        ),
        "active": True,
        "config": {"enforced": True},
    },
    {
        "code": "SOD-2",
        "name": "Two different priority-override approvers",
        "description": "The approver of a priority override MUST differ from the requester.",
        "active": True,
        "config": {"enforced": True},
    },
    {
        "code": "SOD-3",
        "name": "Model editor vs override approver",
        "description": (
            "A user who edited the active scoring model in the current cycle "
            "cannot approve overrides in that cycle."
        ),
        "active": True,
        "config": {"enforced": True},
    },
    {
        "code": "SOD-4",
        "name": "Registry changes require two people",
        "description": (
            "Changes to the Approved Source Registry or AI-processing flags require "
            "two distinct people."
        ),
        "active": True,
        "config": {"enforced": True},
    },
    {
        "code": "SOD-5",
        "name": "Auditor is read-only",
        "description": (
            "The Auditor role is read-only and MUST NOT be combined with any write role."
        ),
        "active": True,
        "config": {"enforced": True, "role": "auditor"},
    },
    {
        "code": "SOD-6",
        "name": "Scenario promotion approvals",
        "description": (
            "Scenario promotion requires approval by someone other than the scenario author."
        ),
        "active": True,
        "config": {"enforced": True},
    },
)


async def _seed_org_units(session: AsyncSession) -> None:
    rows = {row.code: row for row in (await session.execute(select(OrgUnit))).scalars()}
    for code, name, parent_code in ORG_UNITS:
        parent_id = None
        if parent_code:
            parent_result = await session.execute(
                select(OrgUnit.id).where(OrgUnit.code == parent_code)
            )
            parent_id = parent_result.scalar_one_or_none()
        existing = rows.get(code)
        if existing is None:
            session.add(OrgUnit(code=code, name=name, parent_id=parent_id))
        else:
            existing.name = name
            existing.parent_id = parent_id


async def _seed_permissions(session: AsyncSession) -> None:
    existing = {
        (row.role, row.permission): row
        for row in (await session.execute(select(RolePermission))).scalars()
    }
    wanted = {(role, permission) for role, permission, _scope in ROLE_PERMISSIONS}
    for key, current in existing.items():
        if key not in wanted:
            await session.delete(current)
    for role, permission, scope in ROLE_PERMISSIONS:
        existing_row = existing.get((role, permission))
        if existing_row is None:
            session.add(RolePermission(role=role, permission=permission, scope=scope))
        else:
            existing_row.scope = scope


async def _seed_sod_rules(session: AsyncSession) -> None:
    await session.execute(delete(SoDRule))
    session.add_all([SoDRule(**row) for row in _SOD_RULES])


async def _seed_workflow_definitions(session: AsyncSession) -> None:
    for definition in WORKFLOW_DEFINITIONS:
        existing = (
            await session.execute(
                select(WorkflowDefinition).where(
                    WorkflowDefinition.key == definition["key"],
                    WorkflowDefinition.version == definition["version"],
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(WorkflowDefinition(**definition))
        else:
            existing.name = definition["name"]
            existing.active = definition["active"]
            existing.definition = definition["definition"]


async def seed_reference_data(session: AsyncSession) -> None:
    """Ensure Phase 1 reference data exists. Called after ``create_all`` in tests."""
    await _seed_org_units(session)
    await _seed_permissions(session)
    await _seed_sod_rules(session)
    await _seed_workflow_definitions(session)
    await session.commit()
