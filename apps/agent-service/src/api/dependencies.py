"""API dependencies - shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

__all__ = ["verify_bearer", "extract_user_id_from_token"]

VALID_API_KEYS: set = set()


def _get_valid_api_keys() -> set:
    """Get valid API keys from environment variable."""
    global VALID_API_KEYS
    if not VALID_API_KEYS:
        import os

        api_keys_env = os.environ.get("VALID_API_KEYS", "")
        if api_keys_env:
            VALID_API_KEYS = set(k.strip() for k in api_keys_env.split(",") if k.strip())
    return VALID_API_KEYS


def extract_user_id_from_token(token: str) -> str | None:
    """Extract user_id from a simple API token."""
    if not token:
        return None
    if token.startswith("api-key:"):
        return token[8:]
    return token


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
    """Verify the bearer token."""
    valid_keys = _get_valid_api_keys()
    if not valid_keys:
        return
    if http_auth:
        token = http_auth.credentials
        if token in valid_keys:
            return
        user_id = extract_user_id_from_token(token)
        if user_id in valid_keys:
            return
