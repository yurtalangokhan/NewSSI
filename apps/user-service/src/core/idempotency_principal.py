"""Scope idempotency keys to Gateway-authenticated users or machine callers."""

from __future__ import annotations

import hmac

from config_manager import env
from fastapi import Request

from src.core.gateway_identity import gateway_user_id


async def extract_principal_from_gateway(request: Request) -> str | None:
    """Return the trusted principal without validating a bearer token."""
    secret = (env.INTERNAL_SERVICE_TOKEN or "").strip()
    user_id = gateway_user_id(request.headers, secret)
    if user_id:
        return user_id
    supplied = (request.headers.get("x-internal-service-token") or "").strip()
    if secret and supplied and hmac.compare_digest(supplied, secret):
        return "internal-service"
    return None
