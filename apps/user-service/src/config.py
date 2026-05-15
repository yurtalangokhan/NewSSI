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
    KEYCLOAK_ISSUER_URL: str | None = None
    KEYCLOAK_BASE_URL: str | None = None
    KEYCLOAK_REALM: str = "agenticai"
    KEYCLOAK_ADMIN: str = "admin"
    KEYCLOAK_ADMIN_PASSWORD: str = "admin123"
    KEYCLOAK_ADMIN_EMAIL: str | None = None
    KEYCLOAK_CLIENT_ID: str = "agenticai-web"
    KEYCLOAK_AUDIENCE: str | None = None

    AUTH_SECRET: str | None = None
    ENCRYPTION_KEY: str | None = None
    INTERNAL_SERVICE_TOKEN: str | None = None

    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8123"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
