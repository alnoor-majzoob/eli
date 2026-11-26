"""Core execution API."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response

from eil.core.db import AsyncSession, get_db
from eil.modules.execution.models import (
    BenefitMeasurement,
    WorkItemStatus,
    WorkType,
)
from eil.modules.execution.schemas import (
    BenefitMeasurementCreate,
    BenefitMeasurementRead,
    BenefitMeasurementUpdate,
    BenefitRealisationRead,
    BenefitRollupRow,
    WorkItemCreate,
    WorkItemPage,
    WorkItemRead,
    WorkItemUpdate,
    WorkLinkCreate,
    WorkLinkRead,
)
from eil.modules.execution.service import (
    benefit_rollup,
    create_benefit_measurement,
    create_work_item,
    create_work_link,
    delete_work_item,
    delete_work_link,
    get_benefit_measurements,
    get_benefit_realisation,
    get_measurement,
    get_work_item,
    list_work_items,
    list_work_links,
    update_benefit_measurement,
    update_work_item,
)
from eil.modules.identity.rbac import (
    PermissionContext,
    require_any_permission,
    require_permission,
)
from eil.modules.seed_data import DEMAND_CREATE, WORK_EDIT, WORK_VIEW

router = APIRouter(tags=["execution"])

CtxRead = Annotated[PermissionContext, Depends(require_permission(WORK_VIEW))]
CtxWrite = Annotated[PermissionContext, Depends(require_permission(WORK_EDIT))]
CtxCreate = Annotated[PermissionContext, Depends(require_any_permission(WORK_EDIT, DEMAND_CREATE))]
Db = Annotated[AsyncSession, Depends(get_db)]
IfMatch = Annotated[str | None, Header(alias="If-Match")]


def _parse_etag(value: str | None) -> int | None:
    if not value:
        return None
    token = value.strip()
    if token.startswith("W/"):
        token = token[2:]
    token = token.strip('"')
    try:
        return int(token)
    except ValueError as exc:
        from eil.core.errors import AppError

        raise AppError(
            400, "invalid_etag", "Invalid ETag", "If-Match must carry a numeric version."
        ) from exc


def _set_etag(response: Response, item: Any) -> None:
    response.headers["ETag"] = f'"{item.version}"'


@router.get("/items", response_model=WorkItemPage)
async def items_list(
    ctx: CtxRead,
    session: Db,
    type: Annotated[list[WorkType] | None, Query()] = None,
    status: Annotated[list[WorkItemStatus] | None, Query()] = None,
    org_unit_id: Annotated[UUID | None, Query()] = None,
    parent_id: Annotated[UUID | None, Query()] = None,
    owner_id: Annotated[UUID | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> WorkItemPage:
    return await list_work_items(
        session,
        ctx,
        types=type,
        statuses=status,
        org_unit_id=org_unit_id,
        parent_id=parent_id,
        owner_id=owner_id,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.post("/items", response_model=WorkItemRead, status_code=201)
async def item_create(
    ctx: CtxCreate,
    session: Db,
    payload: WorkItemCreate,
    response: Response,
) -> Any:
    item = await create_work_item(session, ctx, payload)
    _set_etag(response, item)
    return item


@router.get("/items/benefit-rollup", response_model=list[BenefitRollupRow])
async def items_benefit_rollup(ctx: CtxRead, session: Db) -> list[BenefitRollupRow]:
    """Benefits → KRs → objectives roll-up for strategic outcome widgets (plan Phase 5, T5.7)."""
    return await benefit_rollup(session, ctx)


@router.get("/items/{item_id}", response_model=WorkItemRead)
async def item_get(
    item_id: UUID,
    ctx: CtxRead,
    session: Db,
    response: Response,
) -> Any:
    item = await get_work_item(session, item_id, ctx)
    _set_etag(response, item)
    return item


@router.patch("/items/{item_id}", response_model=WorkItemRead)
async def item_update(
    item_id: UUID,
    ctx: CtxWrite,
    session: Db,
    payload: WorkItemUpdate,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    item = await get_work_item(session, item_id, ctx)
    updated = await update_work_item(
        session, ctx, item, payload, expected_version=_parse_etag(if_match)
    )
    _set_etag(response, updated)
    return updated


@router.delete("/items/{item_id}", status_code=204)
async def item_delete(item_id: UUID, ctx: CtxWrite, session: Db) -> Response:
    item = await get_work_item(session, item_id, ctx)
    await delete_work_item(session, ctx, item)
    return Response(status_code=204)


@router.get("/items/{item_id}/links", response_model=list[WorkLinkRead])
async def links_list(
    item_id: UUID,
    ctx: CtxRead,
    session: Db,
    direction: Annotated[str, Query(pattern="^(in|out|both)$")] = "both",
) -> list[Any]:
    item = await get_work_item(session, item_id, ctx)
    return list(await list_work_links(session, item, direction))


@router.post("/items/{item_id}/links", response_model=WorkLinkRead, status_code=201)
async def link_create(
    item_id: UUID,
    ctx: CtxWrite,
    session: Db,
    payload: WorkLinkCreate,
) -> Any:
    return await create_work_link(session, ctx, item_id, payload)


@router.delete("/items/{item_id}/links/{link_id}", status_code=204)
async def link_delete(item_id: UUID, link_id: UUID, ctx: CtxWrite, session: Db) -> Response:
    item = await get_work_item(session, item_id, ctx)
    await delete_work_link(session, ctx, item, link_id)
    return Response(status_code=204)


@router.get("/items/{item_id}/benefit-measurements", response_model=list[BenefitMeasurementRead])
async def benefit_measurements(
    item_id: UUID,
    ctx: CtxRead,
    session: Db,
) -> Sequence[BenefitMeasurement]:
    item = await get_work_item(session, item_id, ctx)
    return await get_benefit_measurements(session, item.id)


@router.post(
    "/items/{item_id}/benefit-measurements",
    response_model=BenefitMeasurementRead,
    status_code=201,
)
async def benefit_measurement_create(
    item_id: UUID,
    ctx: CtxWrite,
    session: Db,
    payload: BenefitMeasurementCreate,
) -> BenefitMeasurement:
    item = await get_work_item(session, item_id, ctx)
    return await create_benefit_measurement(session, ctx, item, payload)


@router.patch("/benefit-measurements/{measurement_id}", response_model=BenefitMeasurementRead)
async def benefit_measurement_update(
    measurement_id: UUID,
    ctx: CtxWrite,
    session: Db,
    payload: BenefitMeasurementUpdate,
) -> BenefitMeasurement:
    measurement = await get_measurement(session, measurement_id)
    item = await get_work_item(session, measurement.benefit_id, ctx)
    if item.type != WorkType.BENEFIT:
        from eil.core.errors import AppError

        raise AppError(422, "validation_error", "Validation error", "Item is not a benefit.")
    return await update_benefit_measurement(session, ctx, measurement, payload)


@router.get("/items/{item_id}/benefit-realisation", response_model=BenefitRealisationRead)
async def benefit_realisation(
    item_id: UUID,
    ctx: CtxRead,
    session: Db,
) -> dict[str, Any]:
    item = await get_work_item(session, item_id, ctx)
    if item.type != WorkType.BENEFIT:
        from eil.core.errors import AppError

        raise AppError(422, "validation_error", "Validation error", "Item is not a benefit.")
    return await get_benefit_realisation(session, item)


def _register_type_list(path: str, work_type: WorkType) -> None:
    async def endpoint(
        ctx: CtxRead,
        session: Db,
        status: Annotated[list[WorkItemStatus] | None, Query()] = None,
        parent_id: Annotated[UUID | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> WorkItemPage:
        return await list_work_items(
            session,
            ctx,
            types=[work_type],
            statuses=status,
            parent_id=parent_id,
            limit=limit,
            offset=offset,
        )

    endpoint.__name__ = f"list_{work_type.value}"
    endpoint.__doc__ = f"List {work_type.value} items."
    router.add_api_route(
        path,
        endpoint,
        methods=["GET"],
        response_model=WorkItemPage,
        tags=["execution"],
        name=f"list-{work_type.value}",
    )


for _path, _work_type in (
    ("/objectives", WorkType.OBJECTIVE),
    ("/key-results", WorkType.KEY_RESULT),
    ("/initiatives", WorkType.INITIATIVE),
    ("/demands", WorkType.DEMAND),
    ("/programs", WorkType.PROGRAM),
    ("/projects", WorkType.PROJECT),
    ("/milestones", WorkType.MILESTONE),
    ("/tasks", WorkType.TASK),
    ("/commitments", WorkType.COMMITMENT),
    ("/risks", WorkType.RISK),
    ("/issues", WorkType.ISSUE),
    ("/benefits", WorkType.BENEFIT),
    ("/decisions", WorkType.DECISION),
):
    _register_type_list(_path, _work_type)
