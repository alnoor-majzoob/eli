"""Security hardening (plan §13.3, Phase 9, T9.2).

Covers: CSP + security headers, per-principal/IP rate limiting, CORS lock-down,
host allow-list, SSRF guard on connector URLs, and ingestion URL validation.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
from connectors.sdk.sim import sim_base
from connectors.sdk.urls import URLValidationError, validate_connector_url
from httpx import ASGITransport, AsyncClient

from eil.core.config import Settings
from eil.main import create_app
from eil.modules.integration.ingestion import _safe_external_url
from eil.modules.integration.models import ApprovedSource


def _settings(tmp_path: Path, **overrides) -> Settings:
    base = dict(
        app_env="local",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'security_test.db'}",
        auth_mode="dev",
        outbox_inline_dispatcher=False,
        log_level="WARNING",
        log_format="console",
        object_store_local_dir=tmp_path / "objects",
    )
    return Settings(**{**base, **overrides})


def _get(app, base_url: str = "http://test") -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url=base_url)


# --- CSP + security headers -------------------------------------------------


async def test_csp_header_present(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    for header in (
        "x-content-type-options",
        "x-frame-options",
        "referrer-policy",
        "permissions-policy",
    ):
        assert header in response.headers


# --- Rate limiting -----------------------------------------------------------


async def test_rate_limit_returns_429_after_budget(tmp_path: Path) -> None:
    settings = _settings(tmp_path, rate_limit_requests=2, rate_limit_window_seconds=60)
    app = create_app(settings)
    async with _get(app) as client:
        r1 = await client.get("/")
        r2 = await client.get("/")
        r3 = await client.get("/")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert r3.json()["code"] == "rate_limited"
    assert r3.json()["retry_after"] >= 1


async def test_rate_limit_disabled(tmp_path: Path) -> None:
    settings = _settings(tmp_path, rate_limit_enabled=False, rate_limit_requests=1)
    app = create_app(settings)
    async with _get(app) as client:
        for _ in range(5):
            response = await client.get("/")
            assert response.status_code == 200


# --- CORS lock-down ----------------------------------------------------------


async def test_cors_allows_listed_origin(tmp_path: Path) -> None:
    settings = _settings(tmp_path, cors_origins=["https://web.eil.example"])
    app = create_app(settings)
    async with _get(app) as client:
        response = await client.get("/", headers={"Origin": "https://web.eil.example"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://web.eil.example"


async def test_cors_rejects_unlisted_origin(tmp_path: Path) -> None:
    settings = _settings(tmp_path, cors_origins=["https://web.eil.example"])
    app = create_app(settings)
    async with _get(app) as client:
        response = await client.get("/", headers={"Origin": "https://evil.example"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_origins_reject_wildcard() -> None:
    with pytest.raises(Exception, match="wildcard"):
        Settings(cors_origins=["*"])


# --- Host allow-list ---------------------------------------------------------


async def test_trusted_host_rejected_for_unknown_host(tmp_path: Path) -> None:
    settings = _settings(tmp_path, trusted_hosts=["api.eil.test"])
    app = create_app(settings)
    async with _get(app, base_url="http://evil.example") as client:
        response = await client.get("/")
    assert response.status_code == 400


async def test_trusted_host_allowed(tmp_path: Path) -> None:
    settings = _settings(tmp_path, trusted_hosts=["api.eil.test"])
    app = create_app(settings)
    async with _get(app, base_url="http://api.eil.test") as client:
        response = await client.get("/")
    assert response.status_code == 200


# --- SSRF guard on connector URLs -------------------------------------------


def test_ssrf_rejects_metadata_endpoint() -> None:
    with pytest.raises(URLValidationError):
        validate_connector_url("http://169.254.169.254/latest/meta-data/")


def test_ssrf_rejects_loopback() -> None:
    with pytest.raises(URLValidationError):
        validate_connector_url("http://127.0.0.1:9101")


def test_ssrf_rejects_private_ip() -> None:
    with pytest.raises(URLValidationError):
        validate_connector_url("http://10.0.0.5:9101")


def test_ssrf_rejects_loopback_hostname() -> None:
    with pytest.raises(URLValidationError):
        validate_connector_url("http://localhost:9101")


def test_ssrf_rejects_embedded_credentials() -> None:
    with pytest.raises(URLValidationError):
        validate_connector_url("https://user:pass@eil.example.com/")


def test_ssrf_rejects_non_http_scheme() -> None:
    with pytest.raises(URLValidationError):
        validate_connector_url("file:///etc/passwd")


def test_ssrf_rejects_empty_and_missing_host() -> None:
    with pytest.raises(URLValidationError):
        validate_connector_url("")
    with pytest.raises(URLValidationError):
        validate_connector_url("https:///path")


def test_ssrf_rejects_oversized_url() -> None:
    with pytest.raises(URLValidationError):
        validate_connector_url("https://eil.example.com/" + "a" * 3000)


def test_ssrf_requires_https_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "connectors.sdk.urls.socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    with pytest.raises(URLValidationError):
        validate_connector_url("http://eil.example.com/")


def test_ssrf_accepts_public_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "connectors.sdk.urls.socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    url = validate_connector_url("https://api.eil.example.com/v1")
    assert url == "https://api.eil.example.com/v1"


def test_ssrf_rejects_unresolvable_host(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args, **kwargs):
        raise socket.gaierror("no DNS")

    monkeypatch.setattr("connectors.sdk.urls.socket.getaddrinfo", _raise)
    with pytest.raises(URLValidationError):
        validate_connector_url("https://nonexistent.invalid")


def test_ssrf_allow_private_for_simulators() -> None:
    url = validate_connector_url("http://10.20.30.40:9102", allow_private=True, require_https=False)
    assert url == "http://10.20.30.40:9102"


def test_sim_base_validates_env_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EAM_SIM_URL", "http://10.20.30.40:9102")
    assert sim_base("eam") == "http://10.20.30.40:9102"


# --- Ingestion URL validation ------------------------------------------------


def test_safe_external_url_rejects_unsafe() -> None:
    source = ApprovedSource(type="eam", name="Test", owner="ops")
    assert _safe_external_url("file:///etc/passwd", source) is None
    assert _safe_external_url("", source) is None
    assert _safe_external_url(None, source) is None


def test_safe_external_url_allows_sim_urls() -> None:
    source = ApprovedSource(type="eam", name="Test", owner="ops")
    assert _safe_external_url("http://10.0.0.9/record", source) == "http://10.0.0.9/record"
    assert _safe_external_url("https://eil-sim.example.com/x", source) == (
        "https://eil-sim.example.com/x"
    )
