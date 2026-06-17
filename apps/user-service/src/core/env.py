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
    def KEYCLOAK_CLIENT_SECRET(self) -> str | None:
        return os.environ.get("KEYCLOAK_CLIENT_SECRET")

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

    @property
    def LDAP_ENABLED(self) -> bool:
        return os.environ.get("LDAP_ENABLED", "false").lower() == "true"

    @property
    def LDAP_HOST(self) -> str:
        return os.environ.get("LDAP_HOST", "localhost")

    @property
    def LDAP_PORT(self) -> int:
        return int(os.environ.get("LDAP_PORT", "389"))

    @property
    def LDAP_USE_TLS(self) -> bool:
        return os.environ.get("LDAP_USE_TLS", "false").lower() == "true"

    @property
    def LDAP_BIND_DN(self) -> str | None:
        return os.environ.get("LDAP_BIND_DN")

    @property
    def LDAP_BIND_PASSWORD(self) -> str | None:
        return os.environ.get("LDAP_BIND_PASSWORD")

    @property
    def LDAP_BASE_DN(self) -> str:
        return os.environ.get("LDAP_BASE_DN", "dc=example,dc=com")

    @property
    def LDAP_USER_SEARCH_FILTER(self) -> str:
        return os.environ.get(
            "LDAP_USER_SEARCH_FILTER",
            "(&(objectClass=person)(uid={{username}}))",
        )

    @property
    def LDAP_USER_SEARCH_BASE(self) -> str | None:
        return os.environ.get("LDAP_USER_SEARCH_BASE")

    @property
    def LDAP_ATTRIBUTE_MAP(self) -> str:
        return os.environ.get(
            "LDAP_ATTRIBUTE_MAP",
            '{"username": "uid", "email": "mail", "first_name": "givenName", "last_name": "sn"}',
        )


_env = Env()
