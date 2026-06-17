"""API dependencies - shared FastAPI dependencies."""

from service.AuthService import (
    AuthenticatedUser,
    extract_user_id_from_token,
    require_user,
    require_user_or_internal_service_token,
    verify_api_key,
    verify_bearer,
)

__all__ = [
    "AuthenticatedUser",
    "require_user",
    "require_user_or_internal_service_token",
    "verify_bearer",
    "verify_api_key",
    "extract_user_id_from_token",
]
