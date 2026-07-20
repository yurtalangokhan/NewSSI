from pydantic import BaseModel, Field


class KeycloakRealmSessionUpdate(BaseModel):
    access_token_lifespan: int | None = Field(default=None, ge=1)
    sso_session_idle_timeout: int | None = Field(default=None, ge=1)
    sso_session_max_lifespan: int | None = Field(default=None, ge=1)


class KeycloakConfigUpdate(BaseModel):
    keycloak_enabled: bool | None = None
    keycloak_base_url: str | None = None
    keycloak_issuer_url: str | None = None
    keycloak_realm: str | None = None
    keycloak_admin: str | None = None
    keycloak_admin_password: str | None = None
    keycloak_client_id: str | None = None
    keycloak_login_client_id: str | None = None
    keycloak_client_secret: str | None = None
    external_keycloak: bool | None = None
    external_keycloak_alias: str | None = None
    external_keycloak_display_name: str | None = None
    external_keycloak_base_url: str | None = None
    external_keycloak_issuer_url: str | None = None
    external_keycloak_backend_issuer_url: str | None = None
    external_keycloak_realm: str | None = None
    external_keycloak_client_id: str | None = None
    external_keycloak_client_secret: str | None = None

__all__ = ["KeycloakConfigUpdate", "KeycloakRealmSessionUpdate"]
