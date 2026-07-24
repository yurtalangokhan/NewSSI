from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    SERVICE_NAME: str = "user-service"
    SERVICE_HOST: str = "0.0.0.0"
    SERVICE_PORT: int = 8090

    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: str | None = None
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str | None = None

    KEYCLOAK_ENABLED: bool = False
    EXTERNAL_KEYCLOAK: bool = False
    KEYCLOAK_ISSUER_URL: str | None = None
    KEYCLOAK_BASE_URL: str | None = None
    KEYCLOAK_REALM: str = "agenticai"
    KEYCLOAK_ADMIN: str = "admin"
    KEYCLOAK_ADMIN_PASSWORD: str = "admin123"
    KEYCLOAK_ADMIN_EMAIL: str | None = None
    KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL: str | None = None
    KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD: str | None = None
    KEYCLOAK_CLIENT_ID: str = "agenticai-web"
    KEYCLOAK_LOGIN_CLIENT_ID: str = "agenticai-web"
    KEYCLOAK_CLIENT_SECRET: str | None = None
    KEYCLOAK_AUDIENCE: str | None = None
    KEYCLOAK_REDIRECT_URI: str = "*"
    KEYCLOAK_REDIRECT_URIS: str | None = None
    KEYCLOAK_WEB_ORIGINS: str | None = None
    KEYCLOAK_POST_LOGOUT_REDIRECT_URIS: str = "+"
    EXTERNAL_KEYCLOAK_ALIAS: str = "external-keycloak"
    EXTERNAL_KEYCLOAK_DISPLAY_NAME: str = "External Keycloak"
    EXTERNAL_KEYCLOAK_BASE_URL: str | None = None
    EXTERNAL_KEYCLOAK_ISSUER_URL: str | None = None
    EXTERNAL_KEYCLOAK_BACKEND_ISSUER_URL: str | None = None
    EXTERNAL_KEYCLOAK_REALM: str | None = None
    EXTERNAL_KEYCLOAK_CLIENT_ID: str | None = None
    EXTERNAL_KEYCLOAK_CLIENT_SECRET: str | None = None
    EXTERNAL_KEYCLOAK_ADMIN: str | None = None
    EXTERNAL_KEYCLOAK_ADMIN_PASSWORD: str | None = None

    AUTH_SECRET: str | None = None
    ENCRYPTION_KEY: str | None = None
    INTERNAL_SERVICE_TOKEN: str | None = None

    LDAP_ENABLED: bool = False
    LDAP_HOST: str = "localhost"
    LDAP_PORT: int = 389
    LDAP_USE_TLS: bool = False
    LDAP_BIND_DN: str = ""
    LDAP_BIND_PASSWORD: str = ""
    LDAP_BASE_DN: str = "dc=example,dc=com"
    LDAP_USER_SEARCH_FILTER: str = "(&(objectClass=person)(uid={{username}}))"
    LDAP_USER_SEARCH_BASE: str = ""
    LDAP_ATTRIBUTE_MAP: str = (
        '{"username": "uid", "email": "mail", "first_name": "givenName", "last_name": "sn"}'
    )

    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8123"

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    IDEMPOTENCY_TTL: int = 86400
    IDEMPOTENCY_ENABLED: bool = True

    LOG_LEVEL: str = "INFO"

    @property
    def database_url(self) -> str:
        user = self.POSTGRES_USER or "user_service"
        password = self.POSTGRES_PASSWORD or "user_service_pass"
        host = self.POSTGRES_HOST or "localhost"
        port = self.POSTGRES_PORT or 5432
        db = self.POSTGRES_DB or "user_service"
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

    @property
    def sync_database_url(self) -> str:
        user = self.POSTGRES_USER or "user_service"
        password = self.POSTGRES_PASSWORD or "user_service_pass"
        host = self.POSTGRES_HOST or "localhost"
        port = self.POSTGRES_PORT or 5432
        db = self.POSTGRES_DB or "user_service"
        return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]

    def require_auth_secret(self) -> str:
        if self.AUTH_SECRET:
            return self.AUTH_SECRET
        if not self.KEYCLOAK_ENABLED:
            return "dev-auth-secret-change-in-production-32chars"
        raise ValueError("Required environment variable AUTH_SECRET is not set")

    def require_encryption_key(self) -> str:
        if self.ENCRYPTION_KEY:
            return self.ENCRYPTION_KEY
        return "UKtf1bGCDl8smcVDRM9YekfivWNlsjSB-Mh0d993z40="


@lru_cache
def get_settings() -> Settings:
    return Settings()
