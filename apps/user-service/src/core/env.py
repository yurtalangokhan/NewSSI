import os


def get_env() -> "Env":
    return _env


class Env:
    def __getattr__(self, name: str):
        return os.environ.get(name)

    def get(self, key: str, default=None):
        return os.environ.get(key, default)

    @property
    def KEYCLOAK_ENABLED(self) -> bool:
        return os.environ.get("KEYCLOAK_ENABLED", "false").lower() == "true"

    @property
    def KEYCLOAK_ISSUER_URL(self) -> str | None:
        return os.environ.get("KEYCLOAK_ISSUER_URL")

    @property
    def KEYCLOAK_BASE_URL(self) -> str | None:
        return os.environ.get("KEYCLOAK_BASE_URL")

    @property
    def KEYCLOAK_REALM(self) -> str:
        return os.environ.get("KEYCLOAK_REALM", "agenticai")

    @property
    def KEYCLOAK_ADMIN(self) -> str:
        return os.environ.get("KEYCLOAK_ADMIN", "admin")

    @property
    def KEYCLOAK_ADMIN_PASSWORD(self) -> str:
        return os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin123")

    @property
    def KEYCLOAK_CLIENT_ID(self) -> str:
        return os.environ.get("KEYCLOAK_CLIENT_ID", "agenticai-web")

    @property
    def KEYCLOAK_AUDIENCE(self) -> str | None:
        return os.environ.get("KEYCLOAK_AUDIENCE")

    @property
    def KEYCLOAK_ADMIN_EMAIL(self) -> str | None:
        return os.environ.get("KEYCLOAK_ADMIN_EMAIL")

    @property
    def KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL(self) -> str | None:
        return os.environ.get("KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL")

    @property
    def KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD(self) -> str | None:
        return os.environ.get("KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD")

    @property
    def POSTGRES_USER(self) -> str | None:
        return os.environ.get("POSTGRES_USER")

    @property
    def POSTGRES_PASSWORD(self) -> str | None:
        return os.environ.get("POSTGRES_PASSWORD")

    @property
    def POSTGRES_HOST(self) -> str | None:
        return os.environ.get("POSTGRES_HOST", "localhost")

    @property
    def POSTGRES_PORT(self) -> str | None:
        return os.environ.get("POSTGRES_PORT", "5432")

    @property
    def POSTGRES_DB(self) -> str | None:
        return os.environ.get("POSTGRES_DB")

    @property
    def ENCRYPTION_KEY(self) -> str | None:
        return os.environ.get("ENCRYPTION_KEY")

    @property
    def AUTH_SECRET(self) -> str | None:
        return os.environ.get("AUTH_SECRET")

    @property
    def INTERNAL_SERVICE_TOKEN(self) -> str | None:
        return os.environ.get("INTERNAL_SERVICE_TOKEN")


_env = Env()
