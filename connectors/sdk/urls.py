"""SSRF guards for connector and system URLs (plan §13.3, Phase 9, T9.2).

Fail-closed rules:

- Scheme must be ``http``/``https``. Plain ``http`` is only allowed when the
  caller explicitly opts in via ``allow_private`` (legacy local simulators).
- ``https`` is required unless ``allow_private=True`` and ``require_https``
  is disabled by the caller.
- No embedded credentials, whitespace or over-long URLs.
- The host is resolved; loopback, private, link-local, multicast and reserved
  addresses are rejected unless ``allow_private=True``. Unresolvable hosts are
  rejected unless ``allow_private=True``.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

MAX_URL_LENGTH = 2048


class URLValidationError(ValueError):
    """Raised when a connector URL fails the SSRF safety checks."""


def validate_connector_url(
    url: str,
    *,
    allow_private: bool = False,
    require_https: bool = True,
) -> str:
    """Validate ``url`` against SSRF vectors; return the normalised URL.

    Args:
        url: Candidate URL string.
        allow_private: Permit loopback/private targets and non-https schemes
            (used by local simulators, which run on the LAN by design).
        require_https: Reject non-https schemes in non-allowed mode.
    """
    if not isinstance(url, str):
        raise URLValidationError("URL must be a string")
    url = url.strip()
    if not url or len(url) > MAX_URL_LENGTH:
        raise URLValidationError("URL is empty or too long")
    if any(char.isspace() for char in url):
        raise URLValidationError("URL must not contain whitespace")

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise URLValidationError(f"URL scheme {parsed.scheme!r} is not allowed")
    if parsed.username or parsed.password:
        raise URLValidationError("URL must not contain embedded credentials")
    if require_https and scheme != "https" and not allow_private:
        raise URLValidationError("Only https URLs are allowed")

    host = parsed.hostname
    if not host:
        raise URLValidationError("URL host is empty")
    if allow_private:
        return url

    host = host.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise URLValidationError("Loopback hosts are not allowed")

    try:
        infos = socket.getaddrinfo(
            host,
            parsed.port or (443 if scheme == "https" else 80),
            proto=socket.IPPROTO_TCP,
        )
    except OSError as exc:
        raise URLValidationError(f"Host {host!r} does not resolve") from exc

    for info in infos:
        address = info[4][0]
        ip = ipaddress.ip_address(address)
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise URLValidationError(f"Host {host!r} resolves to private/reserved address {ip}")
    return url
