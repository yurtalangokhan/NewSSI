"""Auth to resolve user object - API Key based authentication with Keycloak JWT support."""

from __future__ import annotations

from typing import Annotated, Any, Optional

import jwt
from fastapi import Depends, Request
from fastapi.exceptions import HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient
from starlette.authentication import BaseUser

from langconnect import config

security = HTTPBearer(auto_error=False)
HTTP_OK = 200

# Internal service token for service-to-service communication
INTERNAL_SERVICE_TOKEN = config.INTERNAL_SERVICE_TOKEN
IS_TESTING = config.IS_TESTING

# Valid API keys from environment
VALID_API_KEYS: set = set()


def _get_valid_api_keys() -> set:
    """Get valid API keys from environment variable."""
    global VALID_API_KEYS
    if not VALID_API_KEYS:
        VALID_API_KEYS = config.parse_valid_api_keys()
    return VALID_API_KEYS


class AuthenticatedUser(BaseUser):
    """An authenticated user following the Starlette authentication model."""

    def __init__(
        self,
        user_id: str,
        display_name: str,
        access_token: str | None = None,
        claims: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the AuthenticatedUser.

        Args:
            user_id: Unique identifier for the user.
            display_name: Display name for the user.
            access_token: User bearer token used for downstream permission checks.
            claims: Decoded JWT claims used for permission checks.
        """
        self.user_id = user_id
        self._display_name = display_name
        self.access_token = access_token
        self.claims = claims or {}

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
    """Verify the API key and return user_id.

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
            credentials = credentials.removeprefix("api-key:")
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
            a.strip() for a in config.KEYCLOAK_AUDIENCE.split(",") if a.strip()
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


def _extract_auth_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    if credentials and credentials.credentials:
        return credentials.credentials

    return (
        request.cookies.get("fastapiusersauth")
        or request.cookies.get("access_token")
        or request.cookies.get("id_token")
        or request.cookies.get("session")
    )


def _claim_permissions(claims: dict[str, Any]) -> set[str]:
    permissions: set[str] = set()

    direct_permissions = claims.get("permissions")
    if isinstance(direct_permissions, list):
        permissions.update(str(p) for p in direct_permissions if p is not None)
    elif isinstance(direct_permissions, str):
        permissions.add(direct_permissions)

    client_id = config.KEYCLOAK_CLIENT_ID or "agenticai-web"
    resource_access = claims.get("resource_access")
    if isinstance(resource_access, dict):
        client_mapping = resource_access.get(client_id)
        if isinstance(client_mapping, dict):
            client_roles = client_mapping.get("roles") or []
            if isinstance(client_roles, list):
                permissions.update(
                    str(role) for role in client_roles if role is not None
                )

    realm_access = claims.get("realm_access")
    if isinstance(realm_access, dict):
        realm_roles = realm_access.get("roles") or []
        if isinstance(realm_roles, list):
            permissions.update(str(role) for role in realm_roles if role is not None)

    return permissions


def _claims_have_permission(claims: dict[str, Any], permission: str) -> bool:
    permissions = _claim_permissions(claims)
    return "*" in permissions or permission in permissions


async def _get_user_service_user(token: str) -> dict[str, Any] | None:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{config.USER_SERVICE_URL.rstrip('/')}/api/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code == HTTP_OK:
            data = response.json()
            return data if isinstance(data, dict) else None
    except Exception:
        return None
    return None


async def resolve_user(
    request: Request,
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(security)
    ] = None,
) -> AuthenticatedUser | None:
    """Resolve user from the credentials or allow internal service access.

    Tries Keycloak JWT validation first (if enabled), then falls through
    to API key validation.
    """
    token = _extract_auth_token(request, credentials)

    if credentials and credentials.scheme != "Bearer":
        raise HTTPException(status_code=401, detail="Invalid authentication scheme")

    if token:
        # Validate Keycloak JWTs before considering legacy API keys. When Keycloak
        # is enabled, invalid Bearer tokens must fail closed instead of falling
        # through to dev/API-key auth.
        if config.KEYCLOAK_ENABLED and config.KEYCLOAK_ISSUER_URL:
            claims = decode_keycloak_token(token)
            sub = claims.get("sub", "")
            if not sub:
                raise HTTPException(status_code=401, detail="Invalid bearer token")

            user_data = await _get_user_service_user(token)
            if user_data:
                user_id = str(user_data.get("id") or sub)
                email = str(
                    user_data.get("email")
                    or claims.get("email")
                    or claims.get("preferred_username")
                    or sub
                )
                return AuthenticatedUser(
                    user_id, email, access_token=token, claims=claims
                )

            email = (
                claims.get("email", "") or claims.get("preferred_username", "") or sub
            )
            return AuthenticatedUser(str(sub), email, access_token=token, claims=claims)

        user_id = verify_api_key(token)
        if user_id:
            return AuthenticatedUser(user_id, user_id, access_token=token)

        raise HTTPException(status_code=401, detail="Invalid API key")

    # Machine-only service calls may still use the internal service token.
    internal_token = request.headers.get("X-Internal-Service-Token")
    if INTERNAL_SERVICE_TOKEN and internal_token == INTERNAL_SERVICE_TOKEN:
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


def require_permission(permission: str):
    """Factory returning a FastAPI dependency that authenticates and checks a permission.

    Usage: ``user = Depends(require_permission("collection:create"))``

    Authenticates via resolve_user, then calls user-service to verify the user's
    role includes the required permission. Dev mode and internal-service bypass.

    Fine-grained permissions live ONLY in the user-service database, not in the
    JWT. The JWT contains only coarse client roles for service-level grouping.
    """

    async def _check(
        request: Request,
        credentials: Annotated[
            Optional[HTTPAuthorizationCredentials], Depends(security)
        ] = None,
    ) -> AuthenticatedUser:
        user = await resolve_user(request=request, credentials=credentials)

        if user.identity in ("dev-user", "internal-service"):
            return user

        from langconnect.authorization import get_authorization_client

        if await get_authorization_client().has_permission(
            user.identity,
            permission,
            user.access_token,
        ):
            return user

        raise HTTPException(
            status_code=403,
            detail=f"Missing required permission: {permission}",
        )

    return _check
