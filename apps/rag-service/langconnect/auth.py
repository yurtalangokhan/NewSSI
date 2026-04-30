"""Auth to resolve user object - Simple API Key based authentication."""

import os
from typing import Annotated, Optional

from fastapi import Depends, Request
from fastapi.exceptions import HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.authentication import BaseUser

security = HTTPBearer(auto_error=False)

# Internal service token for service-to-service communication
INTERNAL_SERVICE_TOKEN = os.environ.get(
    "INTERNAL_SERVICE_TOKEN", "internal-service-key-2026"
)

# Valid API keys from environment
VALID_API_KEYS: set = set()


def _get_valid_api_keys() -> set:
    """Get valid API keys from environment variable."""
    global VALID_API_KEYS
    if not VALID_API_KEYS:
        api_keys_env = os.environ.get("VALID_API_KEYS", "")
        if api_keys_env:
            VALID_API_KEYS = set(
                k.strip() for k in api_keys_env.split(",") if k.strip()
            )
    return VALID_API_KEYS


class AuthenticatedUser(BaseUser):
    """An authenticated user following the Starlette authentication model."""

    def __init__(self, user_id: str, display_name: str) -> None:
        """Initialize the AuthenticatedUser.

        Args:
            user_id: Unique identifier for the user.
            display_name: Display name for the user.
        """
        self.user_id = user_id
        self._display_name = display_name

    @property
    def is_authenticated(self) -> bool:
        """Return True if the user is authenticated."""
        return True

    @property
    def display_name(self) -> str:
        """Return the display name of the user."""
        return self._display_name

    @property
    def identity(self) -> str:
        """Return the identity of the user. This is a unique identifier."""
        return self.user_id


def verify_api_key(credentials: str) -> str | None:
    """
    Verify the API key and return user_id.

    Args:
        credentials: API key string

    Returns:
        user_id if valid, None otherwise
    """
    valid_keys = _get_valid_api_keys()

    # If no keys configured, allow all (dev mode)
    if not valid_keys:
        return "dev-user"

    # Check if credentials is a valid key
    if credentials in valid_keys:
        return credentials

    # Check if it's a token format "api-key:xxx"
    if credentials.startswith("api-key:"):
        key = credentials[8:]
        if key in valid_keys:
            return key

    return None


def resolve_user(
    request: Request,
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(security)
    ] = None,
) -> AuthenticatedUser | None:
    """Resolve user from the credentials or allow internal service access."""

    # Check for internal service token (service-to-service communication)
    internal_token = request.headers.get("X-Internal-Service-Token")
    if internal_token == INTERNAL_SERVICE_TOKEN:
        return AuthenticatedUser("internal-service", "Internal Service")

    # Check if request is from trusted internal host (Docker)
    client_host = request.client.host if request.client else None
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    user_agent = request.headers.get("User-Agent", "")

    # Allow requests from Docker internal network
    if client_host and (
        client_host.startswith("172.")
        or client_host.startswith("192.168.")
        or client_host == "127.0.0.1"
    ):
        if "httpx" in user_agent.lower() or "python" in user_agent.lower():
            return AuthenticatedUser("internal-service", "Internal Service")

    # If no credentials provided - check if we allow anonymous
    if not credentials:
        # For development, allow access
        valid_keys = _get_valid_api_keys()
        if not valid_keys:
            return AuthenticatedUser("dev-user", "Dev User")
        raise HTTPException(status_code=403, detail="API key required")

    if credentials.scheme != "Bearer":
        raise HTTPException(status_code=401, detail="Invalid authentication scheme")

    if not credentials.credentials:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Verify the API key
    user_id = verify_api_key(credentials.credentials)
    if user_id:
        return AuthenticatedUser(user_id, user_id)

    raise HTTPException(status_code=401, detail="Invalid API key")
