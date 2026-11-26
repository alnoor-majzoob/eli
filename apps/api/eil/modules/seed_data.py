"""Seed data for Phase 1: org units, permissions, workflows and SoD rules."""

from __future__ import annotations

from typing import Any, Literal

from eil.modules.identity.demo_users import DEMO_USERS

ORG_UNITS: tuple[tuple[str, str, str | None], ...] = (
    ("exec", "Executive", None),
    ("pmo", "Portfolio Management Office", "exec"),
    ("projects", "Projects", "pmo"),
    ("ops", "Operations", "exec"),
    ("maintenance", "Maintenance", "ops"),
    ("engineering", "Engineering", "ops"),
    ("hsse", "HSSE", "ops"),
    ("it", "Information Technology", "exec"),
    ("audit", "Internal Audit", "exec"),
)

# Permission catalogue (data-driven; see plan §13.1).
DASHBOARD_VIEW = "dashboard.view"
WORK_VIEW = "work.view"
WORK_EDIT = "work.edit"
DEMAND_CREATE = "demand.create"
DEMAND_APPROVE = "demand.approve"
DEPT_HEAD_APPROVE = "dept_head.approve"
SCORING_EDIT = "scoring.edit"
PRIORITY_OVERRIDE = "priority.override"
AI_REVIEW = "ai.review"
ALLOCATION_MANAGE = "allocation.manage"
SCENARIO_PROMOTE = "scenario.promote"
CONNECTOR_MANAGE = "connector.manage"
SOURCE_APPROVE = "source.approve"
AUDIT_VIEW = "audit.view"
ASSISTANT_USE = "assistant.use"
RBAC_ADMIN = "rbac.admin"

ALL_PERMISSIONS: tuple[str, ...] = (
    DASHBOARD_VIEW,
    WORK_VIEW,
    WORK_EDIT,
    DEMAND_CREATE,
    DEMAND_APPROVE,
    DEPT_HEAD_APPROVE,
    SCORING_EDIT,
    PRIORITY_OVERRIDE,
    AI_REVIEW,
    ALLOCATION_MANAGE,
    SCENARIO_PROMOTE,
    CONNECTOR_MANAGE,
    SOURCE_APPROVE,
    AUDIT_VIEW,
    ASSISTANT_USE,
    RBAC_ADMIN,
)

RoleScope = Literal["global", "own_org", "none"]

# Capability matrix from plan §13.1. Scopes: global (enterprise), own_org.
ROLE_PERMISSIONS: tuple[tuple[str, str, RoleScope], ...] = (
    # View enterprise dashboards
    ("executive", DASHBOARD_VIEW, "global"),
    ("portfolio_manager", DASHBOARD_VIEW, "global"),
    ("pmo_analyst", DASHBOARD_VIEW, "global"),
    ("project_manager", DASHBOARD_VIEW, "own_org"),
    ("dept_head", DASHBOARD_VIEW, "own_org"),
    ("resource_manager", DASHBOARD_VIEW, "own_org"),
    ("team_member", DASHBOARD_VIEW, "own_org"),
    ("ai_reviewer", DASHBOARD_VIEW, "own_org"),
    ("auditor", DASHBOARD_VIEW, "global"),
    ("admin", DASHBOARD_VIEW, "global"),
    # Work visibility (read)
    ("executive", WORK_VIEW, "global"),
    ("portfolio_manager", WORK_VIEW, "global"),
    ("pmo_analyst", WORK_VIEW, "global"),
    ("project_manager", WORK_VIEW, "own_org"),
    ("dept_head", WORK_VIEW, "own_org"),
    ("resource_manager", WORK_VIEW, "own_org"),
    ("team_member", WORK_VIEW, "own_org"),
    ("ai_reviewer", WORK_VIEW, "own_org"),
    ("auditor", WORK_VIEW, "global"),
    ("admin", WORK_VIEW, "global"),
    # Create/edit projects & tasks
    ("portfolio_manager", WORK_EDIT, "global"),
    ("pmo_analyst", WORK_EDIT, "global"),
    ("project_manager", WORK_EDIT, "own_org"),
    ("dept_head", WORK_EDIT, "own_org"),
    ("team_member", WORK_EDIT, "own_org"),
    ("admin", WORK_EDIT, "global"),
    # Create/submit demand
    ("executive", DEMAND_CREATE, "global"),
    ("portfolio_manager", DEMAND_CREATE, "global"),
    ("project_manager", DEMAND_CREATE, "global"),
    ("dept_head", DEMAND_CREATE, "global"),
    ("team_member", DEMAND_CREATE, "global"),
    ("pmo_analyst", DEMAND_CREATE, "global"),
    ("admin", DEMAND_CREATE, "global"),
    # Approve demand / stage gate
    ("executive", DEMAND_APPROVE, "global"),
    ("portfolio_manager", DEMAND_APPROVE, "global"),
    ("dept_head", DEPT_HEAD_APPROVE, "own_org"),
    ("admin", DEMAND_APPROVE, "global"),
    # Prioritisation / scoring
    ("portfolio_manager", SCORING_EDIT, "global"),
    ("pmo_analyst", SCORING_EDIT, "global"),
    ("admin", SCORING_EDIT, "global"),
    ("executive", PRIORITY_OVERRIDE, "global"),
    ("portfolio_manager", PRIORITY_OVERRIDE, "global"),
    ("admin", PRIORITY_OVERRIDE, "global"),
    # AI review/accept
    ("portfolio_manager", AI_REVIEW, "global"),
    ("project_manager", AI_REVIEW, "own_org"),
    ("dept_head", AI_REVIEW, "own_org"),
    ("resource_manager", AI_REVIEW, "own_org"),
    ("team_member", AI_REVIEW, "own_org"),
    ("pmo_analyst", AI_REVIEW, "global"),
    ("ai_reviewer", AI_REVIEW, "global"),
    # Allocations / what-if
    ("portfolio_manager", ALLOCATION_MANAGE, "global"),
    ("project_manager", ALLOCATION_MANAGE, "own_org"),
    ("dept_head", ALLOCATION_MANAGE, "own_org"),
    ("resource_manager", ALLOCATION_MANAGE, "global"),
    ("pmo_analyst", ALLOCATION_MANAGE, "global"),
    ("admin", ALLOCATION_MANAGE, "global"),
    # Promote what-if scenario
    ("portfolio_manager", SCENARIO_PROMOTE, "global"),
    ("dept_head", SCENARIO_PROMOTE, "own_org"),
    ("resource_manager", SCENARIO_PROMOTE, "global"),
    ("admin", SCENARIO_PROMOTE, "global"),
    # Connectors, sources and audit
    ("integration_admin", CONNECTOR_MANAGE, "global"),
    ("admin", CONNECTOR_MANAGE, "global"),
    ("admin", SOURCE_APPROVE, "global"),
    ("portfolio_manager", AUDIT_VIEW, "own_org"),
    ("dept_head", AUDIT_VIEW, "own_org"),
    ("pmo_analyst", AUDIT_VIEW, "global"),
    ("integration_admin", AUDIT_VIEW, "own_org"),
    ("auditor", AUDIT_VIEW, "global"),
    ("admin", AUDIT_VIEW, "global"),
    # Assistant and administration
    ("executive", ASSISTANT_USE, "global"),
    ("portfolio_manager", ASSISTANT_USE, "global"),
    ("project_manager", ASSISTANT_USE, "global"),
    ("dept_head", ASSISTANT_USE, "global"),
    ("resource_manager", ASSISTANT_USE, "global"),
    ("team_member", ASSISTANT_USE, "global"),
    ("pmo_analyst", ASSISTANT_USE, "global"),
    ("ai_reviewer", ASSISTANT_USE, "global"),
    ("auditor", ASSISTANT_USE, "global"),
    ("admin", ASSISTANT_USE, "global"),
    ("admin", RBAC_ADMIN, "global"),
)


def _workflow(
    key: str,
    name: str,
    *,
    submit_states: list[str],
    approval_role: str,
    approval_permission: str,
    sla_hours: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    definition = {
        "states": ["draft", "submitted", "approved", "rejected", "cancelled"],
        "initial_state": "draft",
        "transitions": {
            "submit": {
                "from": submit_states,
                "to": "submitted",
                "approval_chain": [
                    {
                        "role": approval_role,
                        "permission": approval_permission,
                        "sla_hours": sla_hours,
                    }
                ],
            },
            "approve": {"from": ["submitted"], "to": "approved"},
            "reject": {"from": ["submitted"], "to": "rejected"},
            "cancel": {"from": ["draft", "submitted", "approved"], "to": "cancelled"},
        },
    }
    if extra:
        definition.update(extra)
    return {"key": key, "name": name, "version": 1, "active": True, "definition": definition}


WORKFLOW_DEFINITIONS: tuple[dict[str, Any], ...] = (
    _workflow(
        "demand_approval",
        "Demand Approval",
        submit_states=["draft", "rejected"],
        approval_role="portfolio_manager",
        approval_permission=DEMAND_APPROVE,
        sla_hours=48,
    ),
    _workflow(
        "stage_gate",
        "Stage Gate Approval",
        submit_states=["draft", "rejected"],
        approval_role="dept_head",
        approval_permission=DEPT_HEAD_APPROVE,
        sla_hours=72,
    ),
    _workflow(
        "change_request",
        "Change Request",
        submit_states=["draft", "active", "rejected"],
        approval_role="dept_head",
        approval_permission=DEPT_HEAD_APPROVE,
        sla_hours=24,
    ),
    _workflow(
        "priority_override",
        "Priority Override",
        submit_states=["draft", "submitted"],
        approval_role="portfolio_manager",
        approval_permission=PRIORITY_OVERRIDE,
        sla_hours=24,
    ),
    _workflow(
        "scenario_promotion",
        "Scenario Promotion",
        submit_states=["draft"],
        approval_role="portfolio_manager",
        approval_permission=SCENARIO_PROMOTE,
        sla_hours=48,
    ),
)

DEMAND_APPROVAL_DEF = WORKFLOW_DEFINITIONS[0]
STAGE_GATE_DEF = WORKFLOW_DEFINITIONS[1]

TYPE_WORKFLOW_KEYS: dict[str, str] = {
    "demand": "demand_approval",
    "project": "stage_gate",
    "program": "stage_gate",
}


def workflow_key_for(item_type: str, requested: str | None = None) -> str:
    if requested:
        return requested
    return TYPE_WORKFLOW_KEYS.get(item_type, "change_request")


def role_names() -> tuple[str, ...]:
    return tuple({user.role for user in DEMO_USERS})
