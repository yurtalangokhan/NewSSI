"""Caller verification for the FastMCP HTTP transport.

Tools-service does not authenticate anyone. Gateway introspects the user token
with Keycloak, applies the route's authorization decision, and forwards the
result as trusted headers. This verifier turns those headers into the
``AccessToken`` FastMCP expects.

FastMCP hands :meth:`verify_token` only the bearer string, so the trusted
headers are read from the active HTTP request via ``get_http_headers``. A
request that did not traverse Gateway has no valid ``x-gateway-token`` and is
rejected — there is no direct-MCP, API-key or development path.
"""

from __future__ import annotations

import time

from config_manager import env
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_http_headers
from security import INTERNAL_SERVICE_USER_ID, resolve_gateway_identity

from .authorization import get_user_service_permissions

INTERNAL_TOKEN_TTL_SECONDS = 3600
GATEWAY_TOKEN_TTL_SECONDS = 300


def _get_internal_service_token() -> str:
    return env.INTERNAL_SERVICE_TOKEN.strip()


class GatewayTokenVerifier(TokenVerifier):
    """Accept only callers Gateway has already authenticated."""

    def __init__(self) -> None:
        settings = env
        super().__init__(base_url=settings.MCP_PUBLIC_BASE_URL, required_scopes=["tool:execute"])

    async def verify_token(self, token: str) -> AccessToken | None:
        headers = get_http_headers(include_all=True)
        identity = resolve_gateway_identity(headers, _get_internal_service_token())
        if identity is None:
            return None

        if identity.is_internal:
            subject = identity.delegated_user_id or INTERNAL_SERVICE_USER_ID
            return AccessToken(
                token=token,
                client_id=subject,
                scopes=["tool:execute"],
                expires_at=int(time.time()) + INTERNAL_TOKEN_TTL_SECONDS,
                claims={"sub": subject, "iss": "gateway", "internal": True},
            )

        scopes = await get_user_service_permissions(token, identity.user_id)
        return AccessToken(
            token=token,
            client_id=identity.user_id,
            scopes=scopes,
            expires_at=int(time.time()) + GATEWAY_TOKEN_TTL_SECONDS,
            claims={
                "sub": identity.user_id,
                "email": identity.email,
                "preferred_username": identity.username,
                "realm_access": {"roles": list(identity.roles)},
                "iss": "gateway",
            },
        )


__all__ = ["GatewayTokenVerifier"]
