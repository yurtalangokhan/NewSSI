from .base import BaseController
from .user_controller import UserController, get_user_controller
from .settings_controller import SettingsController, get_settings_controller
from .user_memory_controller import UserMemoryController, get_user_memory_controller
from .api_key_controller import ApiKeyController, get_api_key_controller


def get_auth_controller():
    """Return the appropriate auth controller based on Keycloak mode.

    - Own Keycloak (EXTERNAL_KEYCLOAK=false): AuthController with full auth + user sync
    - External Keycloak (EXTERNAL_KEYCLOAK=true): ExternalAuthController with OIDC-only flows
    """
    from src.config import get_settings

    settings = get_settings()
    if settings.EXTERNAL_KEYCLOAK:
        from .external_auth_controller import get_external_auth_controller

        return get_external_auth_controller()
    from .auth_controller import get_auth_controller as _get

    return _get()


__all__ = [
    "BaseController",
    "get_auth_controller",
    "UserController",
    "get_user_controller",
    "SettingsController",
    "get_settings_controller",
    "UserMemoryController",
    "get_user_memory_controller",
    "ApiKeyController",
    "get_api_key_controller",
]
