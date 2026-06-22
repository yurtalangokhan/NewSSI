"""Auth to resolve user object - API Key based authentication with Keycloak JWT support."""

import os
from typing import Annotated, Any, Optional

import jwt
from fastapi import Depends, Request
from fastapi.exceptions import HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient
from starlette.authentication import BaseUser

from langconnect import config

security = HTTPBearer(auto_error=False)

# Internal service token for service-to-service communication
INTERNAL_SERVICE_TOKEN = config.INTERNAL_SERVICE_TOKEN
IS_TESTING = config.IS_TESTING

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

    # If no keys configured, tests may still provide bearer values to model
    # distinct users without requiring a configured keyring.
    if not valid_keys:
        if IS_TESTING:
            if credentials.startswith("api-key:"):
                credentials = credentials[8:]
            return credentials or None
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


def decode_keycloak_token(token: str) -> dict[str, Any]:
    """Decode and verify a Keycloak JWT token using JWKS.

    Args:
        token: The JWT token string to decode.

    Returns:
        Decoded claims dictionary from the validated token.

    Raises:
        HTTPException: If the token is invalid or validation fails.
    """
    issuer = config.KEYCLOAK_ISSUER_URL.rstrip("/")
    jwks_url = f"{issuer}/protocol/openid-connect/certs"

    # Build audience list from KEYCLOAK_AUDIENCE and KEYCLOAK_CLIENT_ID
    audiences: list[str] = []
    if config.KEYCLOAK_AUDIENCE:
        audiences = [
            a.strip()
            for a in config.KEYCLOAK_AUDIENCE.split(",")
            if a.strip()
        ]
    if config.KEYCLOAK_CLIENT_ID and config.KEYCLOAK_CLIENT_ID not in audiences:
        audiences.append(config.KEYCLOAK_CLIENT_ID)

    try:
        jwks_client = PyJWKClient(jwks_url, cache_keys=True)
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        claims = jwt.decode(
            jwt=token,
            key=signing_key.key,
            algorithms=["RS256", "RS384", "RS512"],
            issuer=issuer,
            audience=audiences if audiences else None,
            leeway=config.KEYCLOAK_TOKEN_LEEWAY_SECONDS,
            options={
                "verify_aud": bool(audiences),
                "verify_iss": True,
                "verify_exp": True,
            },
        )
        return claims
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid bearer token: {exc}",
        ) from exc


def resolve_user(
    request: Request,
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(security)
    ] = None,
) -> AuthenticatedUser | None:
    """Resolve user from the credentials or allow internal service access.

    Tries Keycloak JWT validation first (if enabled), then falls through
    to API key validation.
    """

    if credentials:
        if credentials.scheme != "Bearer":
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")

        if not credentials.credentials:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Validate Keycloak JWTs before considering legacy API keys. When Keycloak
        # is enabled, invalid Bearer tokens must fail closed instead of falling
        # through to dev/API-key auth.
        if config.KEYCLOAK_ENABLED and config.KEYCLOAK_ISSUER_URL:
            claims = decode_keycloak_token(credentials.credentials)
            sub = claims.get("sub", "")
            email = (
                claims.get("email", "")
                or claims.get("preferred_username", "")
                or sub
            )
            if not sub:
                raise HTTPException(status_code=401, detail="Invalid bearer token")
            return AuthenticatedUser(sub, email)

        user_id = verify_api_key(credentials.credentials)
        if user_id:
            return AuthenticatedUser(user_id, user_id)

        raise HTTPException(status_code=401, detail="Invalid API key")

    # Machine-only service calls may still use the internal service token.
    internal_token = request.headers.get("X-Internal-Service-Token")
    if internal_token == INTERNAL_SERVICE_TOKEN:
        return AuthenticatedUser("internal-service", "Internal Service")

    # If no credentials provided - check if we allow anonymous
    if not credentials:
        if IS_TESTING or (config.KEYCLOAK_ENABLED and config.KEYCLOAK_ISSUER_URL):
            raise HTTPException(status_code=401, detail="Bearer token required")

        # For development, allow access
        valid_keys = _get_valid_api_keys()
        if not valid_keys:
            return AuthenticatedUser("dev-user", "Dev User")
        raise HTTPException(status_code=403, detail="API key required")

    raise HTTPException(status_code=401, detail="Bearer token required")
