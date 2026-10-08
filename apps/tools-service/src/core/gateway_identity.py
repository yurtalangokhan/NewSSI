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

GATEWAY_TOKEN_HEADER = "x-gateway-token"  # noqa: S105 - header name, not a secret
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


__all__ = [
    "INTERNAL_SERVICE_USER_ID",
    "GatewayIdentity",
    "resolve_gateway_identity",
]
