"""FastAPI application factory."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from eil.ai.router import router as ai_router
from eil.core.config import Settings, get_settings
from eil.core.db import create_engine, create_session_factory
from eil.core.errors import register_exception_handlers
from eil.core.logging import setup_logging
from eil.core.middleware import (
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from eil.core.outbox import run_dispatcher_loop
from eil.modules.assistant import models as _assistant_models  # noqa: F401
from eil.modules.assistant.router import router as assistant_router
from eil.modules.audit.guards import install_audit_guards
from eil.modules.audit.router import router as audit_router
from eil.modules.capacity import models as _capacity_models  # noqa: F401
from eil.modules.capacity.router import router as capacity_router
from eil.modules.demo.router import router as demo_router
from eil.modules.execution.router import router as execution_router
from eil.modules.executive.router import router as executive_router
from eil.modules.governance.dashboard_router import router as dashboard_router
from eil.modules.governance.router import router as governance_router
from eil.modules.graph.router import router as graph_router
from eil.modules.health import router as health_router
from eil.modules.identity.router import router as identity_router
from eil.modules.integration.router import router as integration_router
from eil.modules.metrics.router import router as metrics_router
from eil.modules.platform import router as platform_router
from eil.modules.prioritization.router import router as prioritization_router
from eil.modules.risk import models as _risk_models  # noqa: F401
from eil.modules.risk.router import router as risk_router
from eil.observability import MetricsMiddleware, metrics_response, setup_tracing

logger = structlog.get_logger(__name__)

DESCRIPTION = """
Enterprise Execution Intelligence Layer — orchestration and intelligence on top of
systems of record. AI proposes, humans dispose; deterministic engines own every number.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)

        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            await install_audit_guards(engine)
            logger.info("database_ready", dialect=engine.dialect.name)
        except Exception:
            logger.exception("database_unavailable_at_startup")

        dispatcher_task: asyncio.Task[None] | None = None
        if settings.outbox_inline_dispatcher:
            dispatcher_task = asyncio.create_task(
                run_dispatcher_loop(
                    app.state.session_factory,
                    poll_seconds=settings.outbox_poll_seconds,
                ),
                name="outbox-dispatcher",
            )

        setup_tracing(app, engine, settings)

        try:
            yield
        finally:
            if dispatcher_task is not None:
                dispatcher_task.cancel()
                with suppress(asyncio.CancelledError):
                    await dispatcher_task
            await engine.dispose()
            logger.info("application_stopped")

    docs_url = "/docs" if settings.docs_enabled else None
    openapi_url = "/openapi.json" if settings.docs_enabled else None

    app = FastAPI(
        title="EIL — Enterprise Execution Intelligence Layer",
        description=DESCRIPTION,
        version=settings.app_version,
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        enabled=settings.rate_limit_enabled,
        requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "If-Match"],
        expose_headers=["X-Request-ID"],
    )

    register_exception_handlers(app)

    @app.get("/", include_in_schema=False)
    async def index() -> dict[str, Any]:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "env": settings.app_env,
            "api": settings.api_prefix,
            "docs": docs_url,
        }

    if settings.metrics_enabled:
        app.add_api_route("/metrics", metrics_response, include_in_schema=False)

    app.include_router(health_router)
    app.include_router(identity_router, prefix=settings.api_prefix)
    app.include_router(platform_router, prefix=settings.api_prefix)
    app.include_router(assistant_router, prefix=settings.api_prefix)
    app.include_router(audit_router, prefix=settings.api_prefix)
    app.include_router(capacity_router, prefix=settings.api_prefix)
    app.include_router(demo_router, prefix=settings.api_prefix)
    app.include_router(executive_router, prefix=settings.api_prefix)
    app.include_router(execution_router, prefix=settings.api_prefix)
    app.include_router(graph_router, prefix=settings.api_prefix)
    app.include_router(governance_router, prefix=settings.api_prefix)
    app.include_router(ai_router, prefix=settings.api_prefix)
    app.include_router(integration_router, prefix=settings.api_prefix)
    app.include_router(prioritization_router, prefix=settings.api_prefix)
    app.include_router(metrics_router, prefix=settings.api_prefix)
    app.include_router(risk_router, prefix=settings.api_prefix)
    app.include_router(dashboard_router, prefix=settings.api_prefix)

    return app
