"""Principal scope extraction for the idempotency middleware (rag-service).

The idempotency middleware runs before route auth dependencies, so it cannot
rely on the authenticated user object. It reads the identity Gateway
established instead, which is the same source route auth uses.

The extractor is defensive: it never raises. If the request did not arrive
through Gateway it returns ``None`` and the middleware uses the ``anonymous``
scope. Route auth still runs afterward and rejects unauthenticated requests.
"""

from __future__ import annotations

from config_manager import env
from fastapi import Request

from src.shared.gateway_identity import resolve_gateway_identity


async def extract_principal_from_jwt(request: Request) -> str | None:
    """Return a stable principal scope for the idempotency middleware.

    Uses the Gateway-authenticated subject, or ``internal-service`` for machine
    calls. Returns ``None`` when no trusted identity is present.
    """
    identity = resolve_gateway_identity(request.headers, env.INTERNAL_SERVICE_TOKEN)
    if identity is None:
        return None
    return identity.delegated_user_id or identity.user_id
