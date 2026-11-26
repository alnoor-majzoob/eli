"""Enterprise Work Graph API."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from eil.core.db import AsyncSession, get_db
from eil.modules.graph.integrity import check_graph_integrity
from eil.modules.graph.schemas import (
    DownstreamImpactRead,
    GraphIntegrityRead,
    LineageRead,
    NeighborsRead,
    PathRead,
)
from eil.modules.graph.service import downstream_impact, lineage, neighbours, path
from eil.modules.identity.rbac import PermissionContext, require_permission
from eil.modules.seed_data import WORK_VIEW

router = APIRouter(tags=["graph"])

CtxRead = Annotated[PermissionContext, Depends(require_permission(WORK_VIEW))]
Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/graph/nodes/{item_id}/neighbors", response_model=NeighborsRead)
async def graph_neighbors(
    item_id: UUID,
    ctx: CtxRead,
    session: Db,
    direction: Annotated[str, Query(pattern="^(in|out|both)$")] = "both",
    include_virtual: Annotated[bool, Query()] = True,
) -> NeighborsRead:
    """Active edges touching a node, optionally including virtual ``assigned_to`` edges."""
    return await neighbours(session, ctx, item_id, direction, include_virtual)


@router.get("/graph/nodes/{item_id}/lineage", response_model=LineageRead)
async def graph_lineage(
    item_id: UUID,
    ctx: CtxRead,
    session: Db,
    max_depth: Annotated[int, Query(ge=1, le=50)] = 10,
) -> LineageRead:
    """Chain from the node up to the objective (``part_of`` / ``aligns_to``)."""
    return await lineage(session, ctx, item_id, max_depth)


@router.get("/graph/path", response_model=PathRead)
async def graph_path(
    from_id: Annotated[UUID, Query(alias="from")],
    to_id: Annotated[UUID, Query(alias="to")],
    ctx: CtxRead,
    session: Db,
    include_virtual: Annotated[bool, Query()] = True,
) -> PathRead:
    """Shortest path between two nodes (searched in both directions)."""
    return await path(session, ctx, from_id, to_id, include_virtual)


@router.get("/graph/nodes/{item_id}/downstream-impact", response_model=DownstreamImpactRead)
async def graph_downstream_impact(
    item_id: UUID,
    ctx: CtxRead,
    session: Db,
    max_depth: Annotated[int, Query(ge=1, le=20)] = 6,
) -> DownstreamImpactRead:
    """Affected nodes with min depth and strongest-path weight (plan §7.4)."""
    return await downstream_impact(session, ctx, item_id, max_depth)


@router.get("/graph/integrity", response_model=GraphIntegrityRead)
async def graph_integrity(ctx: CtxRead, session: Db) -> GraphIntegrityRead:
    """Orphan-task report, depends_on cycles and duplicate-edge scan."""
    return await check_graph_integrity(session)


__all__ = ["router"]
