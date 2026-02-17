"""Auth to resolve user object."""

import os
from typing import Annotated, Optional

from fastapi import Depends, Request
from fastapi.exceptions import HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from gotrue.types import User
from starlette.authentication import BaseUser
from supabase import create_client

from langconnect import config

security = HTTPBearer(auto_error=False)

# Internal service token for service-to-service communication
INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "internal-service-key-2026")

# Trusted internal networks/hosts (Docker internal)
TRUSTED_HOSTS = ["langgraph-chatbot", "host.docker.internal", "localhost", "127.0.0.1"]


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


def get_current_user(authorization: str) -> User:
    """Authenticate a user by validating their JWT token against Supabase.

    This function verifies the provided JWT token by making a request to Supabase.
    It requires the SUPABASE_URL and SUPABASE_KEY environment variables to be
    properly configured.

    Args:
        authorization: JWT token string to validate

    Returns:
        User: A Supabase User object containing the authenticated user's information

    Raises:
        HTTPException: With status code 500 if Supabase configuration is missing
        HTTPException: With status code 401 if token is invalid or authentication fails
    """
    supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    response = supabase.auth.get_user(authorization)
    user = response.user

    if not user:
        raise HTTPException(status_code=401, detail="Invalid token or user not found")
    return user


def resolve_user(
    request: Request,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)] = None,
) -> AuthenticatedUser | None:
    """Resolve user from the credentials or allow internal service access."""
    
    # Check for internal service token (service-to-service communication)
    internal_token = request.headers.get("X-Internal-Service-Token")
    if internal_token == INTERNAL_SERVICE_TOKEN:
        return AuthenticatedUser("internal-service", "Internal Service")
    
    # Check if request is from trusted internal host
    client_host = request.client.host if request.client else None
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    user_agent = request.headers.get("User-Agent", "")
    
    # Allow requests from Docker internal network
    if client_host and (client_host.startswith("172.") or client_host.startswith("192.168.") or client_host == "127.0.0.1"):
        # Check if it's from our chatbot service
        if "httpx" in user_agent.lower() or "python" in user_agent.lower():
            return AuthenticatedUser("internal-service", "Internal Service")
    
    # If no credentials provided, deny access
    if not credentials:
        raise HTTPException(status_code=403, detail="Not authenticated")
    
    if credentials.scheme != "Bearer":
        raise HTTPException(status_code=401, detail="Invalid authentication scheme")

    if not credentials.credentials:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if config.IS_TESTING:
        if credentials.credentials in {"user1", "user2"}:
            return AuthenticatedUser(credentials.credentials, credentials.credentials)
        raise HTTPException(
            status_code=401, detail="Invalid credentials or user not found"
        )

    user = get_current_user(credentials.credentials)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return AuthenticatedUser(user.id, user.user_metadata.get("name", "User"))
