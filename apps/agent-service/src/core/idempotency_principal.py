"""Principal scope extraction for the idempotency middleware.

The idempotency middleware needs a stable, trusted principal scope so that two
different users can never replay each other's cached responses under the same
``Idempotency-Key``. The middleware runs before route auth dependencies, so it
cannot rely on the authenticated user object. Instead, this module decodes the
bearer/cookie JWT directly and returns the ``sub`` claim.

The extractor is intentionally defensive: it never raises. If the token is
missing or cannot be decoded, it returns ``None`` and the middleware falls back
to the ``anonymous`` scope. Route auth still runs afterward and rejects
unauthenticated requests, so a missing scope here never grants access.
"""

from __future__ import annotations

from fastapi import Request

from core.settings import settings
from service.AuthService import AuthService


def _extract_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization") or ""
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None

    for cookie_name in ("fastapiusersauth", "session", "access_token", "id_token"):
        value = request.cookies.get(cookie_name)
        if value:
            return value
    return None


async def extract_principal_from_jwt(request: Request) -> str | None:
    """Return a stable principal scope for the idempotency middleware.

    Prefers the Keycloak ``sub`` claim. Falls back to the internal service
    token when present (service-to-service calls). Returns ``None`` when no
    identity can be established so the middleware uses the ``anonymous`` scope.
    """
    internal_token = (settings.INTERNAL_SERVICE_TOKEN or "").strip()
    if internal_token:
        header_token = (request.headers.get("X-Internal-Service-Token") or "").strip()
        if header_token == internal_token:
            return "internal-service"

    token = _extract_token(request)
    if not token:
        return None

    if AuthService.is_keycloak_enabled():
        try:
            claims = AuthService.decode_keycloak_token(token)
        except Exception:
            return None
        return claims.get("sub") or claims.get("preferred_username") or claims.get("email")

    # Non-Keycloak mode: use the raw token as the identity (API key or dev).
    if token.startswith("api-key:"):
        return token[8:]
    return token or None
