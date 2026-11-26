"""Application settings.

All behaviour is configuration-driven (plan rule R7). Defaults target the local,
Docker-free development mode documented in ADR-002; the compose stack overrides
them through the environment.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DEV_JWT_SECRET = "dev-only-not-for-production-change-me-32b"

_resolved = Path(__file__).resolve()
# Source layout: <repo>/apps/api/eil/core/config.py -> parents[4] == repo root.
# Container layout: /app/eil/core/config.py -> parents[2] == /app.
try:
    REPO_ROOT = _resolved.parents[4]
except IndexError:
    REPO_ROOT = _resolved.parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / ".data"
SQLITE_PREFIX = "sqlite+aiosqlite:///"

AppEnv = Literal["local", "ci", "demo", "staging", "prod"]
AuthMode = Literal["dev", "oidc"]
LLMMode = Literal["live", "replay", "record"]
ObjectStoreBackend = Literal["local", "s3"]


class Settings(BaseSettings):
    """Environment-backed configuration for the API."""

    model_config = SettingsConfigDict(
        env_file=("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core ---
    app_env: AppEnv = "local"
    app_name: str = "EIL"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    tenant_timezone: str = "Asia/Muscat"
    default_locale: str = "en"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    database_url: str = f"sqlite+aiosqlite:///{DEFAULT_DATA_DIR / 'eil.db'}"
    redis_url: str = ""

    object_store_backend: ObjectStoreBackend = "local"
    object_store_local_dir: Path = DEFAULT_DATA_DIR / "objects"
    object_store_endpoint: str = "http://minio:9000"
    object_store_bucket: str = "eil-artifacts"
    object_store_access_key: str = "changeme"
    object_store_secret_key: str = "changeme"

    # --- Identity ---
    auth_mode: AuthMode = "dev"
    dev_jwt_secret: str = DEFAULT_DEV_JWT_SECRET
    dev_jwt_ttl_minutes: int = 480
    oidc_issuer_url: str = "http://keycloak:8080/realms/eil"
    oidc_discovery_url: str = ""
    oidc_client_id_web: str = "eil-web"
    oidc_audience: str = "eil-api"
    require_mfa: bool = True

    # --- AI / Groq (wired in Phase 4) ---
    ai_enabled: bool = False
    ai_extraction: bool = True
    ai_scoring: bool = True
    ai_assistant: bool = True
    llm_mode: LLMMode = "replay"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    model_fast: str = "llama-3.1-8b-instant"
    model_strong: str = "llama-3.3-70b-versatile"
    model_strong_fallback: str = "openai/gpt-oss-120b"
    model_stt: str = "whisper-large-v3-turbo"
    llm_max_retries: int = 5
    llm_cache_ttl_seconds: int = 86400
    replay_cassette_dir: str = "./seed/cassettes"
    # Per-alias rate limits (env: LLM_RPM_FAST, LLM_TPM_FAST, ...) — plan §8.4.
    llm_rpm_fast: int = 30
    llm_tpm_fast: int = 6000
    llm_rpm_strong: int = 30
    llm_tpm_strong: int = 6000
    llm_rpm_stt: int = 10
    llm_tpm_stt: int = 0

    # --- Integrations (implemented from Phase 3) ---
    connector_mode_m365: Literal["sim", "live"] = "sim"
    connector_mode_p6: Literal["sim", "live"] = "sim"
    connector_mode_eam: Literal["sim", "live"] = "sim"
    connector_mode_erp: Literal["sim", "live"] = "sim"
    connector_mode_hr: Literal["sim", "live"] = "sim"
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""

    # --- Observability ---
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
    metrics_enabled: bool = True
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://otel-collector:4317"

    # --- Runtime ---
    outbox_inline_dispatcher: bool = True
    outbox_poll_seconds: float = 1.0
    sse_enabled: bool = True

    # --- Capacity & resource model (plan §9.2, Phase 6, T6.1-T6.3) ---
    capacity_amber_pct: int = 85
    capacity_red_pct: int = 100
    capacity_sustained_red_weeks: int = 2

    # --- Security (plan §13.3, Phase 9, T9.2) ---
    rate_limit_enabled: bool = True
    rate_limit_requests: int = Field(default=600, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)
    trusted_hosts: list[str] = Field(default_factory=lambda: ["*"])

    @model_validator(mode="after")
    def _check_security_defaults(self) -> Settings:
        """Validate security posture: CORS allow-list + host allow-list (plan §13.3).

        Fails closed outside local/ci/demo environments: no wildcard CORS
        origins and a wildcard trusted-hosts list are rejected.
        """
        normalized = []
        for origin in self.cors_origins:
            origin = origin.strip().rstrip("/")
            if origin.lower() == "*":
                raise ValueError("cors_origins must not contain the '*' wildcard")
            parsed = urlparse(origin if "://" in origin else f"https://{origin}")
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError(f"cors_origins entry {origin!r} is not a valid http(s) origin")
            normalized.append(origin)
        self.cors_origins = normalized

        if self.app_env not in ("local", "ci", "demo"):
            if not self.cors_origins:
                raise ValueError("CORS_ORIGINS must be set outside local/ci/demo environments")
            if "*" in self.trusted_hosts:
                raise ValueError(
                    "TRUSTED_HOSTS must be configured outside local/ci/demo environments"
                )
        return self

    @field_validator("database_url")
    @classmethod
    def _resolve_sqlite_url(cls, value: str) -> str:
        """Resolve relative SQLite paths against the repo root.

        Services run from ``apps/api`` while the documented fallback database
        lives at ``<repo>/.data/eil.db``. Keeping resolution here makes the
        same ``.env`` work from any working directory.
        """
        if not value.startswith(SQLITE_PREFIX):
            return value
        raw = value[len(SQLITE_PREFIX) :]
        if raw.startswith(":memory:") or Path(raw).is_absolute():
            return value
        return f"{SQLITE_PREFIX}{(REPO_ROOT / raw).resolve().as_posix()}"

    @field_validator("object_store_local_dir")
    @classmethod
    def _resolve_object_dir(cls, value: Path) -> Path:
        return value if value.is_absolute() else (REPO_ROOT / value).resolve()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith(("postgresql", "postgres"))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def dev_auth_enabled(self) -> bool:
        return self.auth_mode == "dev" and self.app_env in ("local", "ci", "demo")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def docs_enabled(self) -> bool:
        return self.app_env in ("local", "ci", "demo")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def celery_eager(self) -> bool:
        return not self.redis_url or self.app_env == "ci"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def simulated_systems(self) -> list[str]:
        modes = {
            "m365": self.connector_mode_m365,
            "p6": self.connector_mode_p6,
            "eam": self.connector_mode_eam,
            "erp": self.connector_mode_erp,
            "hr": self.connector_mode_hr,
        }
        return [system for system, mode in modes.items() if mode == "sim"]

    def ensure_local_dirs(self) -> None:
        """Create local-only directories required by fallback backends."""
        if not self.is_postgres:
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        if self.object_store_backend == "local":
            self.object_store_local_dir.mkdir(parents=True, exist_ok=True)

    @property
    def sqlite_path(self) -> Path:
        """Filesystem path of the SQLite database (async URL stripped)."""
        url = self.database_url
        marker = "///"
        if marker in url:
            raw = url.split(marker, 1)[1]
            return Path(raw)
        return DEFAULT_DATA_DIR / "eil.db"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (cleared in tests)."""
    return Settings()
