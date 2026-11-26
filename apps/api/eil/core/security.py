"""Authentication and authorisation primitives.

Local mode uses short-lived HS256 dev tokens (ADR-002). The OIDC path verifies
JWTs against the issuer's JWKS and mirrors what Keycloak/Entra ID will provide
in compose or production.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import httpx
import jwt
import structlog
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from eil.core.config import Settings, get_settings
from eil.core.errors import AppError

logger = structlog.get_logger(__name__)

DEV_ISSUER = "eil-dev"
JWKS_CACHE_TTL_SECONDS = 300

_jwks_uri_cache: dict[str, tuple[float, str]] = {}


class Principal(BaseModel):
    """Authenticated caller identity."""

    subject: str
    name: str
    email: str
    roles: list[str] = Field(default_factory=list)
    org_unit_id: str | None = None
    groups: list[str] = Field(default_factory=list)

    def has_any_role(self, *roles: str) -> bool:
        return bool(set(self.roles) & set(roles))


class DevTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    principal: Principal


def create_dev_token(principal: Principal, settings: Settings) -> DevTokenResponse:
    """Create a locally signed token for local/demo mode only."""
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.dev_jwt_ttl_minutes)
    claims: dict[str, Any] = {
        "sub": principal.subject,
        "name": principal.name,
        "email": principal.email,
        "roles": principal.roles,
        "org_unit_id": principal.org_unit_id,
        "iss": DEV_ISSUER,
        "aud": settings.oidc_audience,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    token = jwt.encode(claims, settings.dev_jwt_secret, algorithm="HS256")
    return DevTokenResponse(
        access_token=token,
        expires_in=int((expires - now).total_seconds()),
        principal=principal,
    )


def decode_dev_token(token: str, settings: Settings) -> Principal:
    payload = jwt.decode(
        token,
        settings.dev_jwt_secret,
        algorithms=["HS256"],
        audience=settings.oidc_audience,
        issuer=DEV_ISSUER,
        options={"require": ["exp", "iat", "sub"]},
    )
    return _principal_from_claims(payload)


async def _resolve_jwks_uri(issuer: str) -> str:
    cached = _jwks_uri_cache.get(issuer)
    now = time.monotonic()
    if cached and cached[0] > now:
        return cached[1]

    url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url)
        response.raise_for_status()
        jwks_uri = response.json().get("jwks_uri")
    if not isinstance(jwks_uri, str):
        raise ValueError(f"OIDC discovery document at {url} has no jwks_uri")
    _jwks_uri_cache[issuer] = (now + JWKS_CACHE_TTL_SECONDS, jwks_uri)
    return jwks_uri


def _signing_key(jwks_uri: str, token: str) -> Any:
    client = jwt.PyJWKClient(jwks_uri, cache_jwk_set=True, lifespan=JWKS_CACHE_TTL_SECONDS)
    return client.get_signing_key_from_jwt(token).key


async def decode_oidc_token(token: str, settings: Settings) -> Principal:
    discovery_url = settings.oidc_discovery_url or settings.oidc_issuer_url
    jwks_uri = await _resolve_jwks_uri(discovery_url)
    key = await asyncio.to_thread(_signing_key, jwks_uri, token)
    payload = jwt.decode(
        token,
        key=key,
        algorithms=["RS256", "RS384", "RS512", "ES256", "ES384"],
        audience=settings.oidc_audience,
        issuer=settings.oidc_issuer_url,
        options={"require": ["exp", "iat", "sub"]},
    )
    return _principal_from_claims(payload, settings=settings)


def _principal_from_claims(payload: dict[str, Any], settings: Settings | None = None) -> Principal:
    roles: list[str] = []

    raw_roles = payload.get("roles")
    if isinstance(raw_roles, list):
        roles.extend(str(role) for role in raw_roles)

    realm_access = payload.get("realm_access")
    if isinstance(realm_access, dict) and isinstance(realm_access.get("roles"), list):
        roles.extend(str(role) for role in realm_access["roles"])

    if settings is not None:
        resource_access = payload.get("resource_access")
        if isinstance(resource_access, dict):
            client = resource_access.get(settings.oidc_client_id_web)
            if isinstance(client, dict) and isinstance(client.get("roles"), list):
                roles.extend(str(role) for role in client["roles"])

    subject = str(payload.get("sub", ""))
    if not subject:
        raise ValueError("token has no subject")

    name = (
        payload.get("name") or payload.get("preferred_username") or payload.get("email") or subject
    )
    raw_groups = payload.get("groups")
    groups = [str(group) for group in (raw_groups or []) if isinstance(group, str)]

    org_unit_id = _optional_str(payload.get("org_unit_id"))
    if org_unit_id is None and groups:
        org_unit_id = next(
            (group.rsplit("/", 1)[-1] for group in groups if group.startswith("/org/")),
            None,
        )

    return Principal(
        subject=subject,
        name=str(name),
        email=str(payload.get("email", "")),
        roles=sorted(set(roles)),
        org_unit_id=org_unit_id,
        groups=groups,
    )


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


async def verify_token(token: str, settings: Settings) -> Principal:
    if settings.dev_auth_enabled:
        return decode_dev_token(token, settings)
    return await decode_oidc_token(token, settings)


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> Principal:
    """FastAPI dependency enforcing a valid bearer token."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(
            401,
            "unauthenticated",
            "Authentication required",
            "Provide an Authorization: Bearer <token> header.",
        )
    settings: Settings = getattr(request.app.state, "settings", None) or get_settings()
    try:
        principal = await verify_token(credentials.credentials, settings)
    except jwt.PyJWTError as exc:
        logger.info("token_rejected", reason=str(exc))
        raise AppError(
            401,
            "invalid_token",
            "Invalid token",
            "The bearer token is invalid or has expired.",
        ) from exc
    except Exception as exc:
        logger.warning("token_verification_failed", error=str(exc))
        raise AppError(
            401,
            "invalid_token",
            "Invalid token",
            "The bearer token could not be verified.",
        ) from exc

    request.state.principal = principal
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def require_roles(*required: str) -> Any:
    """Dependency factory enforcing at least one of the given roles."""

    async def _dependency(principal: CurrentPrincipal) -> Principal:
        if not principal.has_any_role(*required):
            raise AppError(
                403,
                "forbidden",
                "Insufficient permissions",
                "Your role does not grant access to this resource.",
                extra={"required_roles": list(required)},
            )
        return principal

    return _dependency
