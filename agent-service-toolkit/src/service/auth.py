"""
Authentication helpers.

JWT token extraction and bearer-token verification
used as FastAPI dependencies across all protected routes.
"""
import base64
import json
import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core import settings

__all__ = ["verify_bearer", "extract_user_id_from_supabase_token"]

logger = logging.getLogger(__name__)


def extract_user_id_from_supabase_token(token: str) -> str | None:
    """
    Extract user_id (sub claim) from a Supabase JWT token.
    JWT tokens are base64-encoded and contain user info in the payload.
    """
    if not token:
        return None
    try:
        # JWT has 3 parts: header.payload.signature
        parts = token.split(".")
        if len(parts) != 3:
            return None

        # Decode the payload (second part)
        payload_b64 = parts[1]
        # Add padding if necessary
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload_json = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_json)

        # 'sub' is the user ID in Supabase JWTs
        return payload.get("sub")
    except Exception as e:
        logger.warning(f"Failed to extract user_id from token: {e}")
        return None


def verify_bearer(
    http_auth: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(
            HTTPBearer(
                description="Please provide AUTH_SECRET api key.",
                auto_error=False,
            )
        ),
    ],
) -> None:
    """Verify the bearer token matches AUTH_SECRET (if configured)."""
    if not settings.AUTH_SECRET:
        return
    auth_secret = settings.AUTH_SECRET.get_secret_value()
    if not http_auth or http_auth.credentials != auth_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
