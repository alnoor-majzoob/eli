"""Import all ORM models so Alembic and tests see the full metadata."""

from eil.modules.audit.models import AuditLog  # noqa: F401
from eil.modules.execution.models import BenefitMeasurement, WorkItem, WorkLink  # noqa: F401
from eil.modules.governance.models import (  # noqa: F401
    Approval,
    SoDRule,
    WorkflowDefinition,
    WorkflowInstance,
)
from eil.modules.identity.models import OrgUnit, RolePermission, User  # noqa: F401
