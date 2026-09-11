"""Principal scope extraction for the idempotency middleware (rag-service).

The idempotency middleware runs before route auth dependencies, so it cannot
rely on the authenticated user object. This module decodes the bearer/cookie
JWT directly and returns the ``sub`` claim as a stable principal scope.

The extractor is defensive: it never raises. If no identity can be established
it returns ``None`` and the middleware uses the ``anonymous`` scope. Route auth
still runs afterward and rejects unauthenticated requests.
"""

from __future__ import annotations

from fastapi import Request

from langconnect import config
from langconnect.auth import decode_keycloak_token


def _extract_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization") or ""
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None

    for cookie_name in ("fastapiusersauth", "access_token", "id_token", "session"):
        value = request.cookies.get(cookie_name)
        if value:
            return value
    return None


async def extract_principal_from_jwt(request: Request) -> str | None:
    """Return a stable principal scope for the idempotency middleware.

    Prefers the Keycloak ``sub`` claim. Falls back to the internal service
    token when present (service-to-service calls). Returns ``None`` when no
    identity can be established.
    """
    internal_token = (config.INTERNAL_SERVICE_TOKEN or "").strip()
    if internal_token:
        header_token = (
            request.headers.get("X-Internal-Service-Token")
            or request.headers.get("x-internal-token")
            or ""
        ).strip()
        if header_token == internal_token:
            return "internal-service"

    token = _extract_token(request)
    if not token:
        return None

    if config.KEYCLOAK_ENABLED and config.KEYCLOAK_ISSUER_URL:
        try:
            claims = decode_keycloak_token(token)
        except Exception:
            return None
        return claims.get("sub") or claims.get("preferred_username") or claims.get("email")

    # API-key / dev mode.
    if token.startswith("api-key:"):
        return token[8:]
    return token or None
