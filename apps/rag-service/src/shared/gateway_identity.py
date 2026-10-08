"""Caller identity derived from Gateway-set headers.

Gateway is the only component that authenticates a user against Keycloak. It
introspects the token, applies the route's UMA decision, and then forwards the
result as trusted headers. This module turns those headers into an identity; it
never validates a token itself.

``x-gateway-token`` carries ``INTERNAL_SERVICE_TOKEN`` and proves only that a
request traversed Gateway. It is not a machine credential: machine identity
still comes from ``x-internal-service-token``. Gateway strips every header named
here from inbound requests before it runs, so a client cannot forge them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hmac
from urllib.parse import urlsplit

GATEWAY_TOKEN_HEADER = "x-gateway-token"  # noqa: S105 -- a header name, not a secret
GATEWAY_USER_ID_HEADER = "x-gateway-user-id"
GATEWAY_EMAIL_HEADER = "x-gateway-email"
GATEWAY_USERNAME_HEADER = "x-gateway-username"
GATEWAY_ROLES_HEADER = "x-gateway-roles"
INTERNAL_TOKEN_HEADERS = ("x-internal-service-token", "x-internal-token")
DELEGATED_USER_HEADER = "x-user-id"

INTERNAL_SERVICE_USER_ID = "internal-service"
INTERNAL_SERVICE_EMAIL = "internal@service.local"


@dataclass(frozen=True)
class GatewayIdentity:
    """A caller Gateway has already authenticated."""

    user_id: str
    email: str = ""
    username: str | None = None
    roles: tuple[str, ...] = ()
    is_internal: bool = False
    delegated_user_id: str | None = None


def _normalize(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _matches(supplied: str, secret: str) -> bool:
    if not supplied or not secret:
        return False
    return hmac.compare_digest(supplied, secret)


def _split_roles(raw: str) -> tuple[str, ...]:
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


def resolve_gateway_identity(
    headers: Mapping[str, str],
    secret: str | None,
) -> GatewayIdentity | None:
    """Resolve the caller from trusted headers, or None when untrusted.

    Returns None whenever the shared secret is unset or does not match, so an
    unconfigured service fails closed rather than trusting arbitrary headers.
    """
    trusted = (secret or "").strip()
    if not trusted:
        return None

    normalized = _normalize(headers)

    if _matches(normalized.get(GATEWAY_TOKEN_HEADER, "").strip(), trusted):
        user_id = normalized.get(GATEWAY_USER_ID_HEADER, "").strip()
        if user_id:
            username = normalized.get(GATEWAY_USERNAME_HEADER, "").strip()
            return GatewayIdentity(
                user_id=user_id,
                email=normalized.get(GATEWAY_EMAIL_HEADER, "").strip(),
                username=username or None,
                roles=_split_roles(normalized.get(GATEWAY_ROLES_HEADER, "")),
            )

    for header in INTERNAL_TOKEN_HEADERS:
        if _matches(normalized.get(header, "").strip(), trusted):
            delegated = normalized.get(DELEGATED_USER_HEADER, "").strip()
            return GatewayIdentity(
                user_id=INTERNAL_SERVICE_USER_ID,
                email=INTERNAL_SERVICE_EMAIL,
                roles=("internal",),
                is_internal=True,
                delegated_user_id=delegated or None,
            )

    return None


# --- route authorization ------------------------------------------------------


GATEWAY_ROUTE_PREFIXES = (
    "/agent-service",
    "/user-service",
    "/rag-service",
    "/tools-service",
    "/internal/agent-service",
    "/internal/user-service",
    "/internal/rag-service",
    "/internal/tools-service",
)


class GatewayRoutingError(ValueError):
    """Raised when a configured service URL would bypass Gateway."""


def is_gateway_routed(url: str | None) -> bool:
    """True when the URL carries a Gateway route prefix."""
    if not url or not url.strip():
        return False
    path = urlsplit(url.strip()).path.rstrip("/")
    return any(path == prefix or path.startswith(prefix + "/") for prefix in GATEWAY_ROUTE_PREFIXES)


def assert_gateway_routed(urls: dict[str, str | None], *, required: bool = True) -> None:
    """Validate configured service URLs, raising on any that bypass Gateway.
    ``required=False`` tolerates unset values (an optional integration), but a
    value that is set must still route through Gateway.
    """
    offenders: list[str] = []
    for name, url in urls.items():
        value = (url or "").strip()
        if not value:
            if required:
                offenders.append(f"{name} is not set")
            continue
        if not is_gateway_routed(value):
            offenders.append(f"{name}={value!r} does not route through Gateway")
    if offenders:
        raise GatewayRoutingError(
            "Service URLs must go through Gateway "
            "(e.g. http://apisix:8000/internal/user-service). Offending settings: " + "; ".join(offenders)
        )


__all__ = [
    "GATEWAY_ROUTE_PREFIXES",
    "INTERNAL_SERVICE_USER_ID",
    "GatewayIdentity",
    "GatewayRoutingError",
    "assert_gateway_routed",
    "is_gateway_routed",
    "resolve_gateway_identity",
]
