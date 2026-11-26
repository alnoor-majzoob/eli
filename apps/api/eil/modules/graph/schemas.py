"""Graph API schemas — response models for the Enterprise Work Graph."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from eil.modules.execution.models import WorkItemStatus, WorkType


class GraphNodeRead(BaseModel):
    """A graph node: work item or resource (owner) for virtual ``assigned_to`` edges."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: WorkType | None
    title: str
    description: str | None
    status: WorkItemStatus | None
    origin: str | None
    owner_id: UUID | None
    org_unit_id: UUID | None
    attributes: dict[str, Any]
    is_simulated: bool
    created_at: datetime | None
    updated_at: datetime | None


class GraphEdgeRead(BaseModel):
    id: UUID | None
    src_id: UUID
    dst_id: UUID
    link_type: str | None
    weight: Decimal | None
    origin: str | None
    status: str | None
    confidence: Decimal | None
    is_virtual: bool
    src: GraphNodeRead
    dst: GraphNodeRead


class NeighborsRead(BaseModel):
    node_id: UUID
    node: GraphNodeRead
    edges: list[GraphEdgeRead]


class LineageRead(BaseModel):
    items: list[GraphNodeRead]


class PathRead(BaseModel):
    from_id: UUID
    to_id: UUID
    exists: bool
    nodes: list[GraphNodeRead]
    edges: list[GraphEdgeRead]


class ImpactItemRead(BaseModel):
    id: UUID
    type: WorkType
    title: str
    depth: int
    strongest_path_weight: Decimal | None


class DownstreamImpactRead(BaseModel):
    root_id: UUID
    items: list[ImpactItemRead]


class IntegrityCycleRead(BaseModel):
    nodes: list[GraphNodeRead]


class IntegrityOrphanRead(BaseModel):
    id: UUID
    type: WorkType
    title: str
    reason: str


class IntegrityDuplicateEdgeRead(BaseModel):
    src_id: UUID
    dst_id: UUID
    link_type: str
    count: int


class GraphIntegrityRead(BaseModel):
    orphan_tasks: list[IntegrityOrphanRead]
    depends_on_cycles: list[IntegrityCycleRead]
    duplicate_edges: list[IntegrityDuplicateEdgeRead]
