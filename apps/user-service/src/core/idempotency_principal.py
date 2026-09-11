"""Principal scope extraction for the idempotency middleware (user-service).

The idempotency middleware runs before route auth dependencies, so it cannot
rely on the authenticated user object. This module decodes the bearer/cookie
JWT directly and returns the ``sub`` claim as a stable principal scope.

The extractor is defensive: it never raises. If no identity can be established
it returns ``None`` and the middleware uses the ``anonymous`` scope. Route auth
still runs afterward and rejects unauthenticated requests.
"""

from __future__ import annotations

from fastapi import Request

from src.config import get_settings
from src.service import get_auth_service


def _extract_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization") or ""
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None

    for cookie_name in ("access_token", "fastapiusersauth", "session", "id_token"):
        value = request.cookies.get(cookie_name)
        if value:
            return value
    return None


async def extract_principal_from_jwt(request: Request) -> str | None:
    """Return a stable principal scope for the idempotency middleware.

    Prefers the validated token's ``sub`` claim. Falls back to the internal
    service token when present (service-to-service calls). Returns ``None``
    when no identity can be established.
    """
    settings = get_settings()

    internal_token = (settings.INTERNAL_SERVICE_TOKEN or "").strip()
    if internal_token:
        header_token = (request.headers.get("X-Internal-Service-Token") or "").strip()
        if header_token == internal_token:
            return "internal-service"

    token = _extract_token(request)
    if not token:
        return None

    try:
        auth = get_auth_service()
        payload = await auth.validate_token(token)
    except Exception:
        return None

    if payload:
        return payload.get("sub")

    # Dev mode fallback (no Keycloak, no auth secret).
    if not settings.KEYCLOAK_ENABLED and not settings.AUTH_SECRET:
        return "dev-user"

    return None
