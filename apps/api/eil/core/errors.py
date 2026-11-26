"""RFC 7807 problem-detail error handling."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger(__name__)

PROBLEM_BASE_URI = "https://eil.local/problems"
PROBLEM_CONTENT_TYPE = "application/problem+json"


class AppError(Exception):
    """Domain/application error rendered as RFC 7807 problem details."""

    def __init__(
        self,
        status_code: int,
        code: str,
        title: str,
        detail: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.title = title
        self.detail = detail
        self.extra = extra or {}


def problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build an RFC 7807 problem-details response."""
    request_id = getattr(request.state, "request_id", None)
    body: dict[str, Any] = {
        "type": f"{PROBLEM_BASE_URI}/{code}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "code": code,
    }
    if request_id:
        body["request_id"] = request_id
    if extra:
        body.update(extra)
    return JSONResponse(
        status_code=status,
        content=body,
        media_type=PROBLEM_CONTENT_TYPE,
        headers={"X-Request-ID": request_id} if request_id else None,
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return problem_response(
        request,
        status=exc.status_code,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        extra=exc.extra,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _code_for_status(exc.status_code)
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return problem_response(
        request,
        status=exc.status_code,
        code=code,
        title=_title_for_status(exc.status_code),
        detail=detail,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "location": list(error.get("loc", ())),
                "message": error.get("msg", "invalid value"),
                "type": error.get("type", "value_error"),
            }
        )
    return problem_response(
        request,
        status=422,
        code="validation_error",
        title="Validation error",
        detail="One or more request fields are invalid.",
        extra={"errors": errors},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception", path=request.url.path, method=request.method)
    return problem_response(
        request,
        status=500,
        code="internal_error",
        title="Internal server error",
        detail="An unexpected error occurred. The request has been logged.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)


def _title_for_status(status: int) -> str:
    titles = {
        400: "Bad request",
        401: "Unauthenticated",
        403: "Forbidden",
        404: "Not found",
        409: "Conflict",
        429: "Too many requests",
    }
    return titles.get(status, "Request failed")


def _code_for_status(status: int) -> str:
    codes = {
        400: "bad_request",
        401: "unauthenticated",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        429: "rate_limited",
    }
    return codes.get(status, "http_error")
