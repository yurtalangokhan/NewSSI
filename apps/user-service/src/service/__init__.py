from .keycloak_service import KeycloakService, get_keycloak_service
from .ldap_service import LdapService, get_ldap_service
from .user_service import UserService, get_user_service
from .user_settings_service import UserSettingsService, get_user_settings_service
from .user_memory_service import UserMemoryService, get_user_memory_service
from .api_key_service import ApiKeyService, get_api_key_service
from .audit_service import AuditService, get_audit_service


def get_auth_service():
    """Return the appropriate auth service based on Keycloak mode.

    - Own Keycloak (EXTERNAL_KEYCLOAK=false): AuthService with local DB + KC admin
    - External Keycloak (EXTERNAL_KEYCLOAK=true): ExternalAuthService with OIDC-only
    """
    from src.config import get_settings

    settings = get_settings()
    if settings.EXTERNAL_KEYCLOAK:
        from .external_auth_service import get_external_auth_service

        return get_external_auth_service()
    from .auth_service import get_auth_service as _get

    return _get()


__all__ = [
    "KeycloakService",
    "get_keycloak_service",
    "LdapService",
    "get_ldap_service",
    "get_auth_service",
    "UserService",
    "get_user_service",
    "UserSettingsService",
    "get_user_settings_service",
    "UserMemoryService",
    "get_user_memory_service",
    "ApiKeyService",
    "get_api_key_service",
    "AuditService",
    "get_audit_service",
]
