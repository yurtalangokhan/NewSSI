"""Resolve the user identity that Gateway authenticated and authorized."""

import hmac
from collections.abc import Mapping


def gateway_user_id(headers: Mapping[str, str], secret: str | None) -> str | None:
    """Trust only Gateway's proof and subject, never a bearer token alone."""
    expected = (secret or "").strip()
    supplied = (headers.get("x-gateway-token") or "").strip()
    user_id = (headers.get("x-gateway-user-id") or "").strip()
    if not expected or not supplied or not user_id:
        return None
    return user_id if hmac.compare_digest(supplied, expected) else None
