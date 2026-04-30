"""
Authentication helpers.

Simple API key based authentication - no Supabase required.
"""

from core.logger import get_logger

logger = get_logger(__name__)
import logging as _stdlib_logging
logger_stdlib = _stdlib_logging.getLogger(__name__)
import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt import InvalidTokenError, PyJWKClient

__all__ = ["verify_bearer", "extract_user_id_from_token", "verify_api_key"]

logger = get_logger(__name__)

# Valid API keys (comma-separated in environment variable)
VALID_API_KEYS: set = set()
_JWKS_CLIENT: PyJWKClient | None = None


def _get_valid_api_keys() -> set:
    """Get valid API keys from environment variable."""
    global VALID_API_KEYS
    if not VALID_API_KEYS:
        api_keys_env = os.environ.get("VALID_API_KEYS", "")
        if api_keys_env:
            VALID_API_KEYS = set(k.strip() for k in api_keys_env.split(",") if k.strip())
    return VALID_API_KEYS


def _is_keycloak_enabled() -> bool:
    enabled = os.environ.get("KEYCLOAK_ENABLED", "false").lower() == "true"
    return enabled and bool(os.environ.get("KEYCLOAK_ISSUER_URL"))


def _get_keycloak_issuer() -> str:
    issuer = os.environ.get("KEYCLOAK_ISSUER_URL", "").strip()
    if not issuer:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="KEYCLOAK_ISSUER_URL is not configured",
        )
    return issuer.rstrip("/")


def _get_keycloak_jwks_client() -> PyJWKClient:
    global _JWKS_CLIENT
    if _JWKS_CLIENT is None:
        jwks_url = f"{_get_keycloak_issuer()}/protocol/openid-connect/certs"
        _JWKS_CLIENT = PyJWKClient(jwks_url)
    return _JWKS_CLIENT


def _decode_keycloak_token(token: str) -> dict:
    issuer = _get_keycloak_issuer()
    audience_env = os.environ.get("KEYCLOAK_AUDIENCE", "").strip()
    client_id = os.environ.get("KEYCLOAK_CLIENT_ID", "").strip()
    leeway = int(os.environ.get("KEYCLOAK_TOKEN_LEEWAY_SECONDS", "120"))
    audiences = [a.strip() for a in audience_env.split(",") if a.strip()]
    if client_id and client_id not in audiences:
        audiences.append(client_id)

    try:
        signing_key = _get_keycloak_jwks_client().get_signing_key_from_jwt(token)
        base_decode_kwargs = {
            "jwt": token,
            "key": signing_key.key,
            "algorithms": ["RS256", "RS384", "RS512"],
            "issuer": issuer,
            "leeway": leeway,
        }

        # Keycloak often places client identity in `azp` while `aud` can be only `account`.
        # Decode without aud verification first, then validate against aud/azp manually.
        claims = jwt.decode(**base_decode_kwargs, options={"verify_aud": False})

        if not audiences:
            return claims

        token_aud = claims.get("aud")
        aud_list: list[str] = []
        if isinstance(token_aud, str):
            aud_list = [token_aud]
        elif isinstance(token_aud, list):
            aud_list = [str(a) for a in token_aud]

        azp = str(claims.get("azp", ""))
        if any(a in aud_list for a in audiences) or (azp and azp in audiences):
            return claims

        raise InvalidTokenError(
            f"No matching audience found. expected one of {audiences}, got aud={aud_list}, azp={azp}"
        )
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid bearer token: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to validate Keycloak token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token validation failed",
        ) from exc


def _extract_auth_token(
    http_auth: HTTPAuthorizationCredentials | None,
    request: Request,
) -> str | None:
    if http_auth and http_auth.credentials:
        return http_auth.credentials
    return (
        request.cookies.get("fastapiusersauth")
        or request.cookies.get("session")
        or request.cookies.get("id_token")
    )


def extract_user_id_from_token(token: str) -> str | None:
    """
    Extract user_id from a simple API token.
    Format: "api-key:{key}" (base64 encoded)
    Or just use the key directly as user_id.
    """
    if not token:
        return None

    if _is_keycloak_enabled():
        claims = _decode_keycloak_token(token)
        return claims.get("sub") or claims.get("preferred_username") or claims.get("email")

    # If token starts with "api-key:", extract the key
    if token.startswith("api-key:"):
        key = token[8:]  # Remove "api-key:" prefix
        return key

    # Otherwise use the token itself as identifier
    return token


def verify_api_key(
    request: Request,
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
    token = _extract_auth_token(http_auth, request)

    if _is_keycloak_enabled():
        if not token:
            return None
        claims = _decode_keycloak_token(token)
        return claims.get("sub") or claims.get("preferred_username") or claims.get("email")

    # If no API keys configured, allow all (dev mode)
    valid_keys = _get_valid_api_keys()
    if not valid_keys:
        return "dev-user"

    # If no credentials provided
    if not token:
        return None

    # Check if it's a valid API key
    if token in valid_keys:
        return extract_user_id_from_token(token)

    # Check if it's a valid token format
    user_id = extract_user_id_from_token(token)
    if user_id in valid_keys:
        return user_id

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def verify_bearer(
    request: Request,
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
    token = _extract_auth_token(http_auth, request)

    if _is_keycloak_enabled():
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token",
            )
        _decode_keycloak_token(token)
        return

    # If no API keys configured, allow all (dev mode)
    valid_keys = _get_valid_api_keys()
    if not valid_keys:
        return

    # If credentials provided, verify
    if token:
        if token in valid_keys:
            return
        user_id = extract_user_id_from_token(token)
        if user_id in valid_keys:
            return

    # For development, don't block
    # In production, uncomment the following:
    # raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
