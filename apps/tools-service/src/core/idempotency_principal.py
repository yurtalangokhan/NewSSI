"""Scope idempotency by gateway-authenticated or delegated caller identity."""

from config_manager import env
from fastapi import Request
from security import resolve_gateway_identity


async def extract_principal_from_jwt(request: Request) -> str | None:
    """Return no scope when the request has no trusted identity."""
    identity = resolve_gateway_identity(request.headers, env.INTERNAL_SERVICE_TOKEN)
    return (identity.delegated_user_id or identity.user_id) if identity else None
