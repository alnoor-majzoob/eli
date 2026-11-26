"""Request-scoped middleware: correlation IDs, security headers, access logs."""

from __future__ import annotations

import time
import uuid
from collections import deque
from hashlib import sha256
from time import monotonic
from typing import Any

import structlog
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from eil.core.errors import problem_response

logger = structlog.get_logger(__name__)

REQUEST_ID_HEADER = "x-request-id"

# Content-Security-Policy for API responses (plan §13.3, Phase 9, T9.2).
CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self' ws: wss:; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "frame-src 'none'; "
    "upgrade-insecure-requests"
)


class RequestContextMiddleware:
    """Bind a request ID to contextvars and propagate it on the response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        incoming = headers.get(REQUEST_ID_HEADER.encode())
        request_id = incoming.decode() if incoming else uuid.uuid4().hex

        state: dict[str, Any] = scope.setdefault("state", {})
        state["request_id"] = request_id
        state["started_at"] = time.perf_counter()

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=scope.get("method"),
            path=scope.get("path"),
        )

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            structlog.contextvars.clear_contextvars()


class SecurityHeadersMiddleware:
    """Baseline security headers incl. CSP (plan §13.3, Phase 9, T9.2)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
                headers.setdefault("Content-Security-Policy", CSP_POLICY)
            await send(message)

        await self.app(scope, receive, send_wrapper)


class RateLimitMiddleware:
    """Sliding-window rate limiting (plan §13.3, Phase 9, T9.2).

    Keys: hashed bearer token when present (per-principal limits), otherwise
    the client IP. Returns a RFC 7807 ``rate_limited`` problem on exceed.
    """

    _MAX_TRACKED_KEYS = 10_000

    def __init__(
        self,
        app: ASGIApp,
        *,
        requests: int,
        window_seconds: float,
        enabled: bool = True,
    ) -> None:
        self.app = app
        self.enabled = enabled
        self._requests = max(1, requests)
        self._window_seconds = max(0.001, window_seconds)
        self._windows: dict[str, deque[float]] = {}

    def _key(self, scope: Scope) -> str:
        token = ""
        for name, value in scope.get("headers") or []:
            if name.lower() == b"authorization":
                decoded = value.decode("latin-1")
                token = decoded[7:] if decoded[:7].lower() == "bearer " else ""
                break
        if token:
            return "token:" + sha256(token.encode()).hexdigest()[:16]
        client = scope.get("client") or ("", 0)
        return f"ip:{client[0]}"

    def _purge_expired(self, now: float) -> None:
        if len(self._windows) <= self._MAX_TRACKED_KEYS:
            return
        cutoff = now - self._window_seconds
        for key in [k for k, v in self._windows.items() if not v or v[0] <= cutoff]:
            self._windows.pop(key, None)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.enabled or self._requests <= 0:
            await self.app(scope, receive, send)
            return
        now = monotonic()
        key = self._key(scope)
        window = self._windows.setdefault(key, deque())
        self._purge_expired(now)
        while window and window[0] <= now - self._window_seconds:
            window.popleft()
        if len(window) >= self._requests:
            retry_after = int(max(1.0, window[0] + self._window_seconds - now))
            await _rate_limited_response(scope, retry_after)(scope, receive, send)
            return
        window.append(now)
        await self.app(scope, receive, send)


def _rate_limited_response(scope: Scope, retry_after: int) -> JSONResponse:
    request = Request(scope)
    return problem_response(
        request,
        status=429,
        code="rate_limited",
        title="Too many requests",
        detail="Rate limit exceeded; retry later.",
        extra={"retry_after": retry_after},
    )
