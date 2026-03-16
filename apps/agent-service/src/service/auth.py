"""
Authentication helpers.

Simple API key based authentication - no Supabase required.
"""

import logging
import os
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core import settings

__all__ = ["verify_bearer", "extract_user_id_from_token", "verify_api_key"]

logger = logging.getLogger(__name__)

# Valid API keys (comma-separated in environment variable)
VALID_API_KEYS: set = set()


def _get_valid_api_keys() -> set:
    """Get valid API keys from environment variable."""
    global VALID_API_KEYS
    if not VALID_API_KEYS:
        api_keys_env = os.environ.get("VALID_API_KEYS", "")
        if api_keys_env:
            VALID_API_KEYS = set(k.strip() for k in api_keys_env.split(",") if k.strip())
    return VALID_API_KEYS


def extract_user_id_from_token(token: str) -> str | None:
    """
    Extract user_id from a simple API token.
    Format: "api-key:{key}" (base64 encoded)
    Or just use the key directly as user_id.
    """
    if not token:
        return None

    # If token starts with "api-key:", extract the key
    if token.startswith("api-key:"):
        key = token[8:]  # Remove "api-key:" prefix
        return key

    # Otherwise use the token itself as identifier
    return token


def verify_api_key(
    http_auth: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(
            HTTPBearer(
                description="Please provide API key",
                auto_error=False,
            )
        ),
    ],
) -> str | None:
    """
    Verify the API key from bearer token.
    Returns the user_id if valid, None if no auth required.
    """
    # If no API keys configured, allow all (dev mode)
    valid_keys = _get_valid_api_keys()
    if not valid_keys:
        return "dev-user"

    # If no credentials provided
    if not http_auth:
        return None

    token = http_auth.credentials

    # Check if it's a valid API key
    if token in valid_keys:
        return extract_user_id_from_token(token)

    # Check if it's a valid token format
    user_id = extract_user_id_from_token(token)
    if user_id in valid_keys:
        return user_id

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def verify_bearer(
    http_auth: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(
            HTTPBearer(
                description="Please provide API key",
                auto_error=False,
            )
        ),
    ],
) -> None:
    """
    Verify the bearer token - simplified version.
    For full API key verification, use verify_api_key instead.
    """
    # If no API keys configured, allow all (dev mode)
    valid_keys = _get_valid_api_keys()
    if not valid_keys:
        return

    # If credentials provided, verify
    if http_auth:
        token = http_auth.credentials
        if token in valid_keys:
            return
        user_id = extract_user_id_from_token(token)
        if user_id in valid_keys:
            return

    # For development, don't block
    # In production, uncomment the following:
    # raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
