"""Shared environment accessor; uppercase properties preserve configuration keys."""
# ruff: noqa: N802

import json
import os

from .manager import load_environment

load_environment()

#: Used when CORS_ALLOWED_ORIGINS is unset or unparseable.
DEFAULT_ALLOWED_ORIGIN = "http://localhost:3000"


def _int(name: str, default: int | None = None) -> int | None:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _float(name: str, default: float | None = None) -> float | None:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _bool(name: str, default: bool | None = None) -> bool | None:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Required environment variable {name} is not set")
    return value


def parse_allowed_origins(raw_value: str | None) -> list[str]:
    """Read a configured origin list into ``list[str]``.

    Accepts a JSON array, a JSON string, or a comma-separated list, because the
    value arrives from an env file where all three appear in practice. An unset
    or unparseable value falls back to the single development origin rather than
    to ``*``: a wrong CORS config should fail closed, not open.

    This is configuration *parsing*, so it lives here. The rule about which
    origin/credential combinations are safe to serve is a security concern and
    lives in the security package as ``validate_cors_policy``.
    """
    if not raw_value or not raw_value.strip():
        return [DEFAULT_ALLOWED_ORIGIN]
    normalized = raw_value.strip()
    try:
        parsed = json.loads(normalized)
        if isinstance(parsed, str):
            return [parsed]
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    parts = [part.strip().strip("\"'") for part in normalized.split(",")]
    return [part for part in parts if part] or [DEFAULT_ALLOWED_ORIGIN]


class ConfigManager:
    TOOLS_REQUIRED_KEYS = (
        "MCP_HOST",
        "TOOLS_SERVICE_PORT",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_TOOL_SERVICE_USER",
        "POSTGRES_TOOL_SERVICE_PASSWORD",
        "POSTGRES_TOOL_SERVICE_DB",
        "INTERNAL_USER_SERVICE_URL",
    )

    def validate_tools_service(self) -> None:
        for name in self.TOOLS_REQUIRED_KEYS:
            if getattr(self, name) in (None, ""):
                raise ValueError(f"Required environment variable {name} is not set")

    def is_dev(self) -> bool:
        return self.MODE == "dev"

    def require_auth_secret(self) -> str:
        secret = self.AUTHENTICATION_SECRET
        if not secret:
            raise ValueError("AUTHENTICATION_SECRET must be set in environment")
        return secret

    @property
    def database_url(self) -> str:
        return self._user_database_url("asyncpg")

    @property
    def sync_database_url(self) -> str:
        return self._user_database_url("psycopg")

    @property
    def agent_database_url(self) -> str:
        from sqlalchemy import URL

        return URL.create(
            drivername="postgresql",
            username=self.require("POSTGRES_AGENT_SERVICE_USER"),
            password=self.require("POSTGRES_AGENT_SERVICE_PASSWORD"),
            host=self.require("POSTGRES_HOST"),
            port=self.POSTGRES_PORT,
            database=self.require("POSTGRES_AGENT_SERVICE_DB"),
        ).render_as_string(hide_password=False)

    def _user_database_url(self, driver: str) -> str:
        from sqlalchemy import URL

        password = self.POSTGRES_USER_SERVICE_PASSWORD
        if not password:
            raise ValueError("POSTGRES_USER_SERVICE_PASSWORD must be set in environment")
        return URL.create(
            drivername=f"postgresql+{driver}",
            username=self.POSTGRES_USER_SERVICE_USER or "user_service",
            password=password,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_USER_SERVICE_DB,
        ).render_as_string(hide_password=False)

    @property
    def cors_origins(self) -> list[str]:
        raw = os.environ.get(
            "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8123"
        )
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def agent_log_level(self) -> str:
        return os.environ.get("LOG_LEVEL", "WARNING")

    @property
    def tool_postgres_config(self) -> dict[str, str | int | None]:
        return {
            "user": self.POSTGRES_TOOL_SERVICE_USER,
            "password": self.POSTGRES_TOOL_SERVICE_PASSWORD,
            "host": self.POSTGRES_HOST,
            "port": self.POSTGRES_PORT,
            "database": self.POSTGRES_TOOL_SERVICE_DB,
        }

    def get_embeddings(self):
        if self.IS_TESTING:
            from langchain_core.embeddings import DeterministicFakeEmbedding

            return DeterministicFakeEmbedding(size=512)
        if self.EMBEDDING_PROVIDER.lower() == "ollama":
            from langchain_ollama import OllamaEmbeddings

            return OllamaEmbeddings(model=self.OLLAMA_EMBED_MODEL, base_url=self.OLLAMA_BASE_URL)
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings()

    @property
    def DEFAULT_EMBEDDINGS(self):
        if "_default_embeddings" not in self.__dict__:
            self._default_embeddings = self.get_embeddings()
        return self._default_embeddings

    DEFAULT_COLLECTION_NAME = "default_collection"

    @property
    def ALLOWED_ORIGINS(self) -> list[str]:
        return parse_allowed_origins(self.ALLOW_ORIGINS)

    @property
    def MCP_URL_ALLOWLIST(self) -> tuple[str, ...] | None:
        raw = os.environ.get("MCP_URL_ALLOWLIST")
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw.split(",")
        if isinstance(parsed, str):
            parsed = [parsed]
        if not isinstance(parsed, list):
            raise ValueError("MCP_URL_ALLOWLIST must be a list of URLs")
        return tuple(value.strip() for value in parsed if isinstance(value, str) and value.strip())

    @property
    def BASE_URL(self) -> str:
        return f"http://{self.HOST}:{self.AGENT_SERVICE_PORT}"

    @property
    def AVAILABLE_MODELS(self) -> set[str]:
        return {
            model
            for model in (self.DEFAULT_MODEL, self.OLLAMA_MODEL, self.COMPATIBLE_MODEL)
            if model
        }

    def get(self, key: str, default=None):
        return os.environ.get(key, default)

    def require(self, key: str) -> str:
        value = getattr(self, key)
        if value in (None, ""):
            raise ValueError(f"Required environment variable {key} is not set")
        return str(value)

    @property
    def CORS_ALLOWED_ORIGINS(self) -> str:
        return os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000")

    @property
    def LOG_LEVEL(self) -> str:
        return os.environ.get("LOG_LEVEL", "INFO")

    @property
    def INTERNAL_TOOLS_SERVICE_URL(self) -> str | None:
        return os.environ.get("INTERNAL_TOOLS_SERVICE_URL")

    @property
    def INTERNAL_RAG_SERVICE_API_URL(self) -> str | None:
        value = os.environ.get("INTERNAL_RAG_SERVICE_API_URL")
        return value.rstrip("/") if value else None

    @property
    def INTERNAL_USER_SERVICE_URL(self) -> str | None:
        value = os.environ.get("INTERNAL_USER_SERVICE_URL")
        return value.rstrip("/") if value else None

    @property
    def INTERNAL_AGENT_SERVICE_URL(self) -> str | None:
        value = os.environ.get("INTERNAL_AGENT_SERVICE_URL")
        return value.rstrip("/") if value else None

    @property
    def TOOLS_SERVICE_URL(self) -> str | None:
        return os.environ.get("TOOLS_SERVICE_URL")

    @property
    def RAG_SERVICE_API_URL(self) -> str | None:
        return os.environ.get("RAG_SERVICE_API_URL")

    @property
    def RAG_API_URL(self) -> str | None:
        return os.environ.get("RAG_API_URL")

    @property
    def USER_SERVICE_URL(self) -> str | None:
        return os.environ.get("USER_SERVICE_URL")

    @property
    def INTERNAL_SERVICE_TOKEN(self) -> str | None:
        return os.environ.get("INTERNAL_SERVICE_TOKEN")

    @property
    def AUTHENTICATION_SECRET(self) -> str | None:
        return os.environ.get("AUTHENTICATION_SECRET")

    @property
    def AGENT_SERVICE_PORT(self) -> int:
        return _int("AGENT_SERVICE_PORT", 8080)

    @property
    def USER_SERVICE_PORT(self) -> int:
        return _int("USER_SERVICE_PORT", 8090)

    @property
    def RAG_SERVICE_PORT(self) -> int:
        return _int("RAG_SERVICE_PORT", 8083)

    @property
    def TOOLS_SERVICE_PORT(self) -> int:
        return _int("TOOLS_SERVICE_PORT", 8003)

    @property
    def POSTGRES_HOST(self) -> str | None:
        return os.environ.get("POSTGRES_HOST")

    @property
    def POSTGRES_PORT(self) -> int:
        return _int("POSTGRES_PORT", 5432)

    @property
    def POSTGRES_ADMIN_USER(self) -> str | None:
        return os.environ.get("POSTGRES_ADMIN_USER")

    @property
    def POSTGRES_ADMIN_PASSWORD(self) -> str | None:
        return os.environ.get("POSTGRES_ADMIN_PASSWORD")

    @property
    def POSTGRES_AGENT_SERVICE_DB(self) -> str | None:
        return os.environ.get("POSTGRES_AGENT_SERVICE_DB")

    @property
    def POSTGRES_AGENT_SERVICE_USER(self) -> str | None:
        return os.environ.get("POSTGRES_AGENT_SERVICE_USER")

    @property
    def POSTGRES_AGENT_SERVICE_PASSWORD(self) -> str | None:
        return os.environ.get("POSTGRES_AGENT_SERVICE_PASSWORD")

    @property
    def POSTGRES_RAG_SERVICE_DB(self) -> str | None:
        return os.environ.get("POSTGRES_RAG_SERVICE_DB")

    @property
    def POSTGRES_RAG_SERVICE_USER(self) -> str | None:
        return os.environ.get("POSTGRES_RAG_SERVICE_USER")

    @property
    def POSTGRES_RAG_SERVICE_PASSWORD(self) -> str | None:
        return os.environ.get("POSTGRES_RAG_SERVICE_PASSWORD")

    @property
    def POSTGRES_USER_SERVICE_DB(self) -> str | None:
        return os.environ.get("POSTGRES_USER_SERVICE_DB")

    @property
    def POSTGRES_USER_SERVICE_USER(self) -> str | None:
        return os.environ.get("POSTGRES_USER_SERVICE_USER")

    @property
    def POSTGRES_USER_SERVICE_PASSWORD(self) -> str | None:
        return os.environ.get("POSTGRES_USER_SERVICE_PASSWORD")

    @property
    def POSTGRES_TOOL_SERVICE_DB(self) -> str | None:
        return os.environ.get("POSTGRES_TOOL_SERVICE_DB")

    @property
    def POSTGRES_TOOL_SERVICE_USER(self) -> str | None:
        return os.environ.get("POSTGRES_TOOL_SERVICE_USER")

    @property
    def POSTGRES_TOOL_SERVICE_PASSWORD(self) -> str | None:
        return os.environ.get("POSTGRES_TOOL_SERVICE_PASSWORD")

    @property
    def NEO4J_URI(self) -> str | None:
        return os.environ.get("NEO4J_URI")

    @property
    def NEO4J_USERNAME(self) -> str | None:
        return os.environ.get("NEO4J_USERNAME")

    @property
    def NEO4J_PASSWORD(self) -> str | None:
        return os.environ.get("NEO4J_PASSWORD")

    @property
    def NEO4J_PLUGINS(self) -> str | None:
        return os.environ.get("NEO4J_PLUGINS")

    @property
    def NEO4J_HEAP_INITIAL_SIZE(self) -> str | None:
        return os.environ.get("NEO4J_HEAP_INITIAL_SIZE")

    @property
    def NEO4J_HEAP_MAX_SIZE(self) -> str | None:
        return os.environ.get("NEO4J_HEAP_MAX_SIZE")

    @property
    def NEO4J_PAGECACHE_SIZE(self) -> str | None:
        return os.environ.get("NEO4J_PAGECACHE_SIZE")

    @property
    def NEO4J_PROCEDURES_UNRESTRICTED(self) -> str | None:
        return os.environ.get("NEO4J_PROCEDURES_UNRESTRICTED")

    @property
    def NEO4J_PROCEDURES_ALLOWLIST(self) -> str | None:
        return os.environ.get("NEO4J_PROCEDURES_ALLOWLIST")

    @property
    def APISIX_IMAGE_TAG(self) -> str | None:
        return os.environ.get("APISIX_IMAGE_TAG")

    @property
    def APISIX_HTTP_PORT(self) -> str | None:
        return os.environ.get("APISIX_HTTP_PORT")

    @property
    def GATEWAY_KEYCLOAK_CLIENT_ID(self) -> str:
        return _required("GATEWAY_KEYCLOAK_CLIENT_ID")

    @property
    def GATEWAY_KEYCLOAK_CLIENT_SECRET(self) -> str:
        return _required("GATEWAY_KEYCLOAK_CLIENT_SECRET")

    @property
    def USER_SERVICE_UPSTREAM_ADDR(self) -> str | None:
        return os.environ.get("USER_SERVICE_UPSTREAM_ADDR")

    @property
    def AGENT_SERVICE_UPSTREAM_ADDR(self) -> str | None:
        return os.environ.get("AGENT_SERVICE_UPSTREAM_ADDR")

    @property
    def RAG_SERVICE_UPSTREAM_ADDR(self) -> str | None:
        return os.environ.get("RAG_SERVICE_UPSTREAM_ADDR")

    @property
    def TOOLS_SERVICE_UPSTREAM_ADDR(self) -> str | None:
        return os.environ.get("TOOLS_SERVICE_UPSTREAM_ADDR")

    @property
    def LLM_PROVIDER_API_ENCRYPTION_KEY(self) -> str | None:
        return os.environ.get("LLM_PROVIDER_API_ENCRYPTION_KEY")

    # One Fernet key per class of stored secret, so a leaked key opens only its
    # own data.
    @property
    def MCP_CREDENTIAL_ENCRYPTION_KEY(self) -> str | None:
        return os.environ.get("MCP_CREDENTIAL_ENCRYPTION_KEY")

    @property
    def MCP_OAUTH_ENCRYPTION_KEY(self) -> str | None:
        return os.environ.get("MCP_OAUTH_ENCRYPTION_KEY")

    @property
    def MAIL_CONFIG_ENCRYPTION_KEY(self) -> str | None:
        return os.environ.get("MAIL_CONFIG_ENCRYPTION_KEY")

    @property
    def USER_API_KEY_ENCRYPTION_KEY(self) -> str | None:
        return os.environ.get("USER_API_KEY_ENCRYPTION_KEY")

    @property
    def SYSTEM_SETTINGS_ENCRYPTION_KEY(self) -> str | None:
        return os.environ.get("SYSTEM_SETTINGS_ENCRYPTION_KEY")

    @property
    def CONNECTOR_CONFIG_ENCRYPTION_KEY(self) -> str | None:
        return os.environ.get("CONNECTOR_CONFIG_ENCRYPTION_KEY")

    @property
    def KEYCLOAK_BASE_URL(self) -> str | None:
        return os.environ.get("KEYCLOAK_BASE_URL")

    @property
    def KEYCLOAK_REALM(self) -> str:
        return _required("KEYCLOAK_REALM")

    @property
    def KEYCLOAK_ISSUER_URL(self) -> str | None:
        return os.environ.get("KEYCLOAK_ISSUER_URL")

    @property
    def KEYCLOAK_USER_SERVICE_CLIENT_ID(self) -> str:
        return _required("KEYCLOAK_USER_SERVICE_CLIENT_ID")

    @property
    def KEYCLOAK_USER_SERVICE_CLIENT_SECRET(self) -> str | None:
        return os.environ.get("KEYCLOAK_USER_SERVICE_CLIENT_SECRET")

    @property
    def KEYCLOAK_USER_SERVICE_AUDIENCE(self) -> str | None:
        return os.environ.get("KEYCLOAK_USER_SERVICE_AUDIENCE")

    @property
    def KEYCLOAK_REDIRECT_URI(self) -> str | None:
        return os.environ.get("KEYCLOAK_REDIRECT_URI")

    @property
    def KEYCLOAK_REDIRECT_URIS(self) -> str | None:
        return os.environ.get("KEYCLOAK_REDIRECT_URIS")

    @property
    def KEYCLOAK_POST_LOGOUT_REDIRECT_URIS(self) -> str | None:
        return os.environ.get("KEYCLOAK_POST_LOGOUT_REDIRECT_URIS")

    @property
    def KEYCLOAK_DB_VENDOR(self) -> str | None:
        return os.environ.get("KEYCLOAK_DB_VENDOR")

    @property
    def KEYCLOAK_DB_HOST(self) -> str | None:
        return os.environ.get("KEYCLOAK_DB_HOST")

    @property
    def KEYCLOAK_DB_NAME(self) -> str | None:
        return os.environ.get("KEYCLOAK_DB_NAME")

    @property
    def KEYCLOAK_ADMIN(self) -> str:
        return os.environ.get("KEYCLOAK_ADMIN", "admin")

    @property
    def KEYCLOAK_ADMIN_PASSWORD(self) -> str | None:
        return os.environ.get("KEYCLOAK_ADMIN_PASSWORD")

    @property
    def KEYCLOAK_HEALTH_ENABLED(self) -> bool:
        return os.environ.get("KEYCLOAK_HEALTH_ENABLED", "true").lower() == "true"

    @property
    def KEYCLOAK_HOSTNAME_STRICT(self) -> bool:
        return os.environ.get("KEYCLOAK_HOSTNAME_STRICT", "false").lower() == "true"

    @property
    def KEYCLOAK_WEB_ORIGIN(self) -> str | None:
        return os.environ.get("KEYCLOAK_WEB_ORIGIN")

    @property
    def KEYCLOAK_WEB_ORIGINS(self) -> str | None:
        return os.environ.get("KEYCLOAK_WEB_ORIGINS")

    @property
    def KEYCLOAK_TEST_USER(self) -> str | None:
        return os.environ.get("KEYCLOAK_TEST_USER")

    @property
    def KEYCLOAK_TEST_EMAIL(self) -> str | None:
        return os.environ.get("KEYCLOAK_TEST_EMAIL")

    @property
    def KEYCLOAK_TEST_PASSWORD(self) -> str | None:
        return os.environ.get("KEYCLOAK_TEST_PASSWORD")

    @property
    def KEYCLOAK_DEFAULT_ADMIN_USER(self) -> str | None:
        return os.environ.get("KEYCLOAK_DEFAULT_ADMIN_USER")

    @property
    def KEYCLOAK_DEFAULT_ADMIN_EMAIL(self) -> str | None:
        return os.environ.get("KEYCLOAK_DEFAULT_ADMIN_EMAIL")

    @property
    def KEYCLOAK_DEFAULT_ADMIN_PASSWORD(self) -> str | None:
        return os.environ.get("KEYCLOAK_DEFAULT_ADMIN_PASSWORD")

    @property
    def KEYCLOAK_DEFAULT_ADMIN_FIRST_NAME(self) -> str | None:
        return os.environ.get("KEYCLOAK_DEFAULT_ADMIN_FIRST_NAME")

    @property
    def KEYCLOAK_DEFAULT_ADMIN_LAST_NAME(self) -> str | None:
        return os.environ.get("KEYCLOAK_DEFAULT_ADMIN_LAST_NAME")

    @property
    def KEYCLOAK_DEFAULT_ADMIN_REALM_ROLE(self) -> str | None:
        return os.environ.get("KEYCLOAK_DEFAULT_ADMIN_REALM_ROLE")

    @property
    def KEYCLOAK_PUBLIC_HOSTNAME(self) -> str | None:
        return os.environ.get("KEYCLOAK_PUBLIC_HOSTNAME")

    @property
    def KEYCLOAK_PUBLIC_PORT(self) -> str | None:
        return os.environ.get("KEYCLOAK_PUBLIC_PORT")

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
    def KEYCLOAK_LOGIN_CLIENT_ID(self) -> str:
        return _required("KEYCLOAK_LOGIN_CLIENT_ID")

    @property
    def VECTOR_DB_PROVIDER(self) -> str:
        return os.environ.get("VECTOR_DB_PROVIDER", "milvus")

    @property
    def MILVUS_HOST(self) -> str | None:
        return os.environ.get("MILVUS_HOST")

    @property
    def MILVUS_PORT(self) -> int:
        return _int("MILVUS_PORT", 9765)

    @property
    def MILVUS_USER(self) -> str | None:
        return os.environ.get("MILVUS_USER")

    @property
    def MILVUS_PASSWORD(self) -> str | None:
        return os.environ.get("MILVUS_PASSWORD")

    @property
    def MILVUS_BIND_ADDR(self) -> str | None:
        return os.environ.get("MILVUS_BIND_ADDR")

    @property
    def MILVUS_ETCD_ENDPOINTS(self) -> str | None:
        return os.environ.get("MILVUS_ETCD_ENDPOINTS")

    @property
    def MILVUS_MINIO_ADDRESS(self) -> str | None:
        return os.environ.get("MILVUS_MINIO_ADDRESS")

    @property
    def MILVUS_ETCD_AUTO_COMPACTION_MODE(self) -> str | None:
        return os.environ.get("MILVUS_ETCD_AUTO_COMPACTION_MODE")

    @property
    def MILVUS_ETCD_AUTO_COMPACTION_RETENTION(self) -> str | None:
        return os.environ.get("MILVUS_ETCD_AUTO_COMPACTION_RETENTION")

    @property
    def MILVUS_ETCD_QUOTA_BACKEND_BYTES(self) -> str | None:
        return os.environ.get("MILVUS_ETCD_QUOTA_BACKEND_BYTES")

    @property
    def MILVUS_ETCD_SNAPSHOT_COUNT(self) -> str | None:
        return os.environ.get("MILVUS_ETCD_SNAPSHOT_COUNT")

    @property
    def MINIO_ROOT_USER(self) -> str | None:
        return os.environ.get("MINIO_ROOT_USER")

    @property
    def MINIO_ROOT_PASSWORD(self) -> str | None:
        return os.environ.get("MINIO_ROOT_PASSWORD")

    @property
    def MINIO_HOST(self) -> str | None:
        return os.environ.get("MINIO_HOST")

    @property
    def MINIO_PORT(self) -> int:
        return _int("MINIO_PORT", 10000)

    @property
    def MINIO_ACCESS_KEY(self) -> str | None:
        return os.environ.get("MINIO_ACCESS_KEY")

    @property
    def MINIO_SECRET_KEY(self) -> str | None:
        return os.environ.get("MINIO_SECRET_KEY")

    @property
    def MINIO_BUCKET(self) -> str | None:
        return os.environ.get("MINIO_BUCKET")

    @property
    def MINIO_SECURE(self) -> bool:
        return _bool("MINIO_SECURE", False)

    @property
    def OLLAMA_IMAGE_TAG(self) -> str | None:
        return os.environ.get("OLLAMA_IMAGE_TAG")

    @property
    def OLLAMA_BASE_URL(self) -> str:
        return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    @property
    def OLLAMA_MODEL(self) -> str:
        return os.environ.get("OLLAMA_MODEL", "llama3.1:8b")

    @property
    def OLLAMA_EMBED_MODEL(self) -> str:
        return os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    @property
    def DEFAULT_MODEL(self) -> str:
        return os.environ.get("DEFAULT_MODEL", "llama3.1:8b")

    @property
    def EMBEDDING_PROVIDER(self) -> str:
        return os.environ.get("EMBEDDING_PROVIDER", "ollama")

    @property
    def REDIS_HOST(self) -> str | None:
        return os.environ.get("REDIS_HOST")

    @property
    def REDIS_PORT(self) -> int:
        return _int("REDIS_PORT", 6379)

    @property
    def REDIS_DB(self) -> int:
        return _int("REDIS_DB", 0)

    @property
    def REDIS_PASSWORD(self) -> str | None:
        return os.environ.get("REDIS_PASSWORD")

    @property
    def IDEMPOTENCY_TTL(self) -> int:
        return _int("IDEMPOTENCY_TTL", 86400)

    @property
    def IDEMPOTENCY_ENABLED(self) -> bool:
        return _bool("IDEMPOTENCY_ENABLED", True)

    @property
    def IDEMPOTENCY_LOCK_TTL(self) -> int:
        return _int("IDEMPOTENCY_LOCK_TTL", 10)

    @property
    def IDEMPOTENCY_WAIT_TIMEOUT(self) -> float:
        return _float("IDEMPOTENCY_WAIT_TIMEOUT", 10.0)

    @property
    def LDAP_ENABLED(self) -> bool:
        return _bool("LDAP_ENABLED", False)

    @property
    def LDAP_HOST(self) -> str:
        return os.environ.get("LDAP_HOST", "localhost")

    @property
    def LDAP_PORT(self) -> int:
        return _int("LDAP_PORT", 389)

    @property
    def LDAP_USE_TLS(self) -> bool:
        return _bool("LDAP_USE_TLS", False)

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
    def LDAP_ATTRIBUTE_MAP(self) -> str:
        return os.environ.get(
            "LDAP_ATTRIBUTE_MAP",
            '{"username": "uid", "email": "mail", "first_name": "givenName", "last_name": "sn"}',
        )

    @property
    def WEB_DOMAIN(self) -> str | None:
        return os.environ.get("WEB_DOMAIN")

    @property
    def AUTH_TYPE(self) -> str | None:
        return os.environ.get("AUTH_TYPE")

    @property
    def AGENT_SERVICE_URL(self) -> str | None:
        return os.environ.get("AGENT_SERVICE_URL")

    @property
    def RAG_SERVICE_URL(self) -> str | None:
        return os.environ.get("RAG_SERVICE_URL")

    @property
    def OVERRIDE_API_PRODUCTION(self) -> bool:
        return os.environ.get("OVERRIDE_API_PRODUCTION", "true").lower() == "true"

    @property
    def VALID_API_KEYS(self) -> str | None:
        return os.environ.get("VALID_API_KEYS")

    @property
    def NEXT_PUBLIC_CLOUD_ENABLED(self) -> bool:
        return os.environ.get("NEXT_PUBLIC_CLOUD_ENABLED", "false").lower() == "true"

    @property
    def NEXT_PUBLIC_ENABLE_PAID_EE_FEATURES(self) -> bool:
        return os.environ.get("NEXT_PUBLIC_ENABLE_PAID_EE_FEATURES", "false").lower() == "true"

    @property
    def NEXT_PUBLIC_TEST_ENV(self) -> bool:
        return os.environ.get("NEXT_PUBLIC_TEST_ENV", "false").lower() == "true"

    @property
    def EXTERNAL_KEYCLOAK(self) -> bool:
        return _bool("EXTERNAL_KEYCLOAK", False)

    @property
    def EXTERNAL_KEYCLOAK_ALIAS(self) -> str:
        return os.environ.get("EXTERNAL_KEYCLOAK_ALIAS", "external-keycloak")

    @property
    def EXTERNAL_KEYCLOAK_DISPLAY_NAME(self) -> str:
        return os.environ.get("EXTERNAL_KEYCLOAK_DISPLAY_NAME", "External Keycloak")

    @property
    def EXTERNAL_KEYCLOAK_BASE_URL(self) -> str | None:
        return os.environ.get("EXTERNAL_KEYCLOAK_BASE_URL")

    @property
    def EXTERNAL_KEYCLOAK_ISSUER_URL(self) -> str | None:
        return os.environ.get("EXTERNAL_KEYCLOAK_ISSUER_URL")

    @property
    def EXTERNAL_KEYCLOAK_BACKEND_ISSUER_URL(self) -> str | None:
        return os.environ.get("EXTERNAL_KEYCLOAK_BACKEND_ISSUER_URL")

    @property
    def EXTERNAL_KEYCLOAK_REALM(self) -> str | None:
        return os.environ.get("EXTERNAL_KEYCLOAK_REALM")

    @property
    def EXTERNAL_KEYCLOAK_CLIENT_ID(self) -> str | None:
        return os.environ.get("EXTERNAL_KEYCLOAK_CLIENT_ID")

    @property
    def EXTERNAL_KEYCLOAK_CLIENT_SECRET(self) -> str | None:
        return os.environ.get("EXTERNAL_KEYCLOAK_CLIENT_SECRET")

    @property
    def EXTERNAL_KEYCLOAK_ADMIN(self) -> str | None:
        return os.environ.get("EXTERNAL_KEYCLOAK_ADMIN")

    @property
    def EXTERNAL_KEYCLOAK_ADMIN_PASSWORD(self) -> str | None:
        return os.environ.get("EXTERNAL_KEYCLOAK_ADMIN_PASSWORD")

    @property
    def KEYCLOAK_CLIENT_ID(self) -> str:
        return _required("KEYCLOAK_CLIENT_ID")

    @property
    def LDAP_USER_SEARCH_BASE(self) -> str | None:
        return os.environ.get("LDAP_USER_SEARCH_BASE")

    @property
    def PERMISSION_MANIFEST_ROOT(self) -> str | None:
        return os.environ.get("PERMISSION_MANIFEST_ROOT")

    @property
    def POSTGRES_USER(self) -> str | None:
        return os.environ.get("POSTGRES_USER")

    @property
    def POSTGRES_PASSWORD(self) -> str | None:
        return os.environ.get("POSTGRES_PASSWORD")

    @property
    def POSTGRES_DB(self) -> str | None:
        return os.environ.get("POSTGRES_DB")

    @property
    def HOST(self) -> str:
        return os.environ.get("HOST", "0.0.0.0")

    @property
    def AGENT_URL(self) -> str | None:
        return os.environ.get("AGENT_URL")

    @property
    def MODE(self) -> str | None:
        return os.environ.get("MODE")

    @property
    def KEYCLOAK_AUDIENCE(self) -> str | None:
        return os.environ.get("KEYCLOAK_AUDIENCE")

    @property
    def KEYCLOAK_TOKEN_LEEWAY_SECONDS(self) -> int:
        return _int("KEYCLOAK_TOKEN_LEEWAY_SECONDS", 120)

    @property
    def KEYCLOAK_CLIENT_SECRET(self) -> str | None:
        return os.environ.get("KEYCLOAK_CLIENT_SECRET")

    @property
    def COMPATIBLE_BASE_URL(self) -> str | None:
        return os.environ.get("COMPATIBLE_BASE_URL")

    @property
    def COMPATIBLE_MODEL(self) -> str | None:
        return os.environ.get("COMPATIBLE_MODEL")

    @property
    def COMPATIBLE_API_KEY(self) -> str | None:
        return os.environ.get("COMPATIBLE_API_KEY")

    @property
    def USE_FAKE_MODEL(self) -> str | None:
        return os.environ.get("USE_FAKE_MODEL")

    @property
    def GITHUB_PAT(self) -> str | None:
        return os.environ.get("GITHUB_PAT")

    @property
    def LANGFUSE_TRACING(self) -> bool:
        return _bool("LANGFUSE_TRACING", False)

    @property
    def LANGFUSE_HOST(self) -> str:
        return os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

    @property
    def LANGFUSE_PUBLIC_KEY(self) -> str | None:
        return os.environ.get("LANGFUSE_PUBLIC_KEY")

    @property
    def LANGFUSE_SECRET_KEY(self) -> str | None:
        return os.environ.get("LANGFUSE_SECRET_KEY")

    @property
    def LANGCHAIN_TRACING_V2(self) -> bool:
        return _bool("LANGCHAIN_TRACING_V2", False)

    @property
    def LANGCHAIN_ENDPOINT(self) -> str:
        return os.environ.get("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")

    @property
    def LANGCHAIN_API_KEY(self) -> str | None:
        return os.environ.get("LANGCHAIN_API_KEY")

    @property
    def LANGCHAIN_PROJECT(self) -> str:
        return os.environ.get("LANGCHAIN_PROJECT", "default")

    @property
    def GRACEFUL_SHUTDOWN_TIMEOUT(self) -> int:
        return _int("GRACEFUL_SHUTDOWN_TIMEOUT", 30)

    @property
    def OPENWEATHERMAP_API_KEY(self) -> str | None:
        return os.environ.get("OPENWEATHERMAP_API_KEY")

    @property
    def OPENAI_API_KEY(self) -> str | None:
        return os.environ.get("OPENAI_API_KEY")

    @property
    def DEEPGRAM_API_KEY(self) -> str | None:
        return os.environ.get("DEEPGRAM_API_KEY")

    @property
    def ELEVENLABS_API_KEY(self) -> str | None:
        return os.environ.get("ELEVENLABS_API_KEY")

    @property
    def VOICE_STT_PROVIDER(self) -> str | None:
        return os.environ.get("VOICE_STT_PROVIDER")

    @property
    def VOICE_TTS_PROVIDER(self) -> str | None:
        return os.environ.get("VOICE_TTS_PROVIDER")

    @property
    def AWS_KB_ID(self) -> str | None:
        return os.environ.get("AWS_KB_ID")

    @property
    def MCP_OAUTH_REDIRECT_BASE(self) -> str:
        # No fallback: this is where a remote authorization server delivers
        # authorization codes. A default of http://localhost:3000 meant a
        # deployment that never set it did not fail -- it pointed the flow
        # at whatever was listening on the browser's own machine, in
        # cleartext. MCPOAuthService._redirect_uri refuses an empty value.
        return os.environ.get("MCP_OAUTH_REDIRECT_BASE", "")

    @property
    def MCP_EXTERNAL_ENABLED(self) -> bool:
        return _bool("MCP_EXTERNAL_ENABLED", True)

    @property
    def MCP_OAUTH_HTTP_TIMEOUT(self) -> float:
        return _float("MCP_OAUTH_HTTP_TIMEOUT", 30.0)

    @property
    def MCP_OAUTH_DEFAULT_TOKEN_TTL_SECONDS(self) -> int:
        return _int("MCP_OAUTH_DEFAULT_TOKEN_TTL_SECONDS", 3600)

    @property
    def MCP_OAUTH_SESSION_TTL_SECONDS(self) -> int:
        return _int("MCP_OAUTH_SESSION_TTL_SECONDS", 600)

    @property
    def MCP_OAUTH_CLIENT_NAME(self) -> str:
        """``client_name`` sent during dynamic client registration."""
        return os.environ.get("MCP_OAUTH_CLIENT_NAME", "Agentic AI")

    @property
    def LOG_FORMAT(self) -> str:
        return os.environ.get("LOG_FORMAT", "text")

    @property
    def LOG_OUTPUT(self) -> str:
        return os.environ.get("LOG_OUTPUT", "console")

    @property
    def LOG_FILE_PATH(self) -> str:
        return os.environ.get("LOG_FILE_PATH", "/var/log/agent-service/app.log")

    @property
    def LOG_MAX_SIZE(self) -> int:
        return _int("LOG_MAX_SIZE", 10485760)

    @property
    def LOG_BACKUP_COUNT(self) -> int:
        return _int("LOG_BACKUP_COUNT", 5)

    @property
    def LOG_INCLUDE_SOURCE(self) -> bool:
        """Whether a record carries the module, function, and line that wrote it."""
        return bool(_bool("LOG_INCLUDE_SOURCE", True))

    @property
    def LOG_QUIET_LOGGERS(self) -> list[str]:
        """Extra loggers pinned to WARNING, on top of each service's own policy.

        Third-party loggers that narrate every request are noise in a shipped
        stream; the access log belongs to the gateway. A comma-separated list
        keeps the value writable in an env file.
        """
        raw = os.environ.get("LOG_QUIET_LOGGERS", "")
        return [name.strip() for name in raw.split(",") if name.strip()]

    @property
    def LOG_SYSLOG_ADDRESS(self) -> str:
        """``host:port`` of the syslog daemon, as a destination option."""
        return os.environ.get("LOG_SYSLOG_ADDRESS", "localhost:514")

    @property
    def LOG_SYSLOG_FACILITY(self) -> str:
        """Syslog facility the records are attributed to."""
        return os.environ.get("LOG_SYSLOG_FACILITY", "user")

    @property
    def LOG_EXTERNAL_URL(self) -> str | None:
        """Ingest URL of the log platform, when one is selected.

        Optional: with no platform selected, ``LOG_OUTPUT`` stays on a local
        destination and this stays unset.
        """
        return os.environ.get("LOG_EXTERNAL_URL") or None

    @property
    def LOG_EXTERNAL_BEARER_TOKEN(self) -> str | None:
        """Bearer credential for the log platform, when the platform requires one."""
        return os.environ.get("LOG_EXTERNAL_BEARER_TOKEN") or None

    @property
    def LOG_EXTERNAL_BATCH_SIZE(self) -> int:
        """Records delivered per platform call."""
        return int(_int("LOG_EXTERNAL_BATCH_SIZE", 100))

    @property
    def LOG_EXTERNAL_FLUSH_INTERVAL(self) -> float:
        """Seconds a partial batch waits before it is delivered anyway."""
        return float(_float("LOG_EXTERNAL_FLUSH_INTERVAL", 5.0))

    @property
    def LOG_EXTERNAL_MAX_QUEUE(self) -> int:
        """Records held while the platform is unavailable before the oldest is dropped."""
        return int(_int("LOG_EXTERNAL_MAX_QUEUE", 1000))

    @property
    def LOG_EXTERNAL_MAX_RETRIES(self) -> int:
        """Delivery attempts per batch before the batch is counted as lost."""
        return int(_int("LOG_EXTERNAL_MAX_RETRIES", 3))

    @property
    def LOG_EXTERNAL_RETRY_BACKOFF(self) -> float:
        """Seconds before the first retry; doubles on each further attempt."""
        return float(_float("LOG_EXTERNAL_RETRY_BACKOFF", 0.5))

    @property
    def LOG_EXTERNAL_SHUTDOWN_TIMEOUT(self) -> float:
        """Seconds the process waits for a final flush before exiting anyway."""
        return float(_float("LOG_EXTERNAL_SHUTDOWN_TIMEOUT", 10.0))

    @property
    def LOG_ELASTICSEARCH_INDEX(self) -> str | None:
        """Fixed Elasticsearch index; unset means one index per service."""
        return os.environ.get("LOG_ELASTICSEARCH_INDEX") or None

    @property
    def OTEL_ENABLED(self) -> bool:
        """Whether the service produces traces and OTLP metrics at all."""
        return bool(_bool("OTEL_ENABLED", False))

    @property
    def OTEL_EXPORTER_OTLP_ENDPOINT(self) -> str | None:
        """OTLP/http endpoint of the telemetry collector."""
        return os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or None

    @property
    def OTEL_EXPORTER_OTLP_HEADERS(self) -> list[tuple[str, str]]:
        """Collector credentials as ``Key=Value`` pairs, comma-separated."""
        raw = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")
        pairs: list[tuple[str, str]] = []
        for part in raw.split(","):
            key, separator, value = part.strip().partition("=")
            if separator:
                pairs.append((key, value))
        return pairs

    @property
    def OTEL_TRACES_SAMPLE_RATIO(self) -> float:
        """Fraction of requests traced, 0.0 to 1.0."""
        return float(_float("OTEL_TRACES_SAMPLE_RATIO", 1.0))

    @property
    def OTEL_METRICS_ENABLED(self) -> bool:
        """Whether OTLP metrics are exported alongside traces."""
        return bool(_bool("OTEL_METRICS_ENABLED", False))

    @property
    def OTEL_METRICS_EXPORT_INTERVAL(self) -> int:
        """Milliseconds between metric exports."""
        return int(_int("OTEL_METRICS_EXPORT_INTERVAL", 60000))

    @property
    def PLAYGROUND_RETENTION_DAYS(self) -> int:
        return _int("PLAYGROUND_RETENTION_DAYS", 30)

    @property
    def PLAYGROUND_RETENTION_POLL_INTERVAL_SECONDS(self) -> int:
        return _int("PLAYGROUND_RETENTION_POLL_INTERVAL_SECONDS", 86400)

    @property
    def PLAYGROUND_RETENTION_STARTUP_DELAY_SECONDS(self) -> int:
        return _int("PLAYGROUND_RETENTION_STARTUP_DELAY_SECONDS", 10)

    @property
    def AGENT_RECURSION_LIMIT(self) -> int:
        return _int("AGENT_RECURSION_LIMIT", 150)

    @property
    def ALLOW_ORIGINS(self) -> str:
        return os.environ.get("ALLOW_ORIGINS", "")

    @property
    def API_VERSIONING_CONFIG(self) -> str | None:
        return os.environ.get("API_VERSIONING_CONFIG")

    @property
    def CONNECTOR_POSTGRES_ENDPOINTS(self) -> str:
        return os.environ.get("CONNECTOR_POSTGRES_ENDPOINTS", "{}")

    # In-process connector syncs (packages/connector-py) run by agent-service.
    @property
    def CONNECTOR_MAX_CONCURRENT_SYNCS(self) -> int:
        return _int("CONNECTOR_MAX_CONCURRENT_SYNCS", 1)

    @property
    def CONNECTOR_SYNC_BATCH_SIZE(self) -> int:
        return _int("CONNECTOR_SYNC_BATCH_SIZE", 200)

    @property
    def CONNECTOR_SYNC_TIMEOUT_SECONDS(self) -> float | None:
        # A day by default, so a source that hangs gives its slot back; 0 means no limit.
        seconds = _float("CONNECTOR_SYNC_TIMEOUT_SECONDS", 86400.0)
        return seconds if seconds and seconds > 0 else None

    @property
    def CONNECTOR_SCHEDULER_POLL_SECONDS(self) -> int:
        return _int("CONNECTOR_SCHEDULER_POLL_SECONDS", 30)

    @property
    def CONNECTORS_ENABLED(self) -> str | None:
        return os.environ.get("CONNECTORS_ENABLED") or None

    @property
    def CONNECTORS_DISABLED(self) -> str | None:
        return os.environ.get("CONNECTORS_DISABLED") or None

    @property
    def COOKIE_SECURE(self) -> bool:
        return _bool("COOKIE_SECURE", False)

    @property
    def CRAWLER_MAX_RETRIES(self) -> int:
        return _int("CRAWLER_MAX_RETRIES", 3)

    @property
    def CRAWLER_RETRY_BACKOFF_FACTOR(self) -> float:
        return _float("CRAWLER_RETRY_BACKOFF_FACTOR", 0.5)

    @property
    def DOCUMENT_TOOLS_ENABLED(self) -> bool:
        return _bool("DOCUMENT_TOOLS_ENABLED", True)

    @property
    def DOCUMENT_TOOLS_RICH_OPTIONS(self) -> bool:
        return _bool("DOCUMENT_TOOLS_RICH_OPTIONS", True)

    @property
    def MERMAID_RENDER_TIMEOUT_SECONDS(self) -> float:
        return _float("MERMAID_RENDER_TIMEOUT_SECONDS", 10.0)

    @property
    def MERMAID_RENDER_WORKERS(self) -> int:
        return _int("MERMAID_RENDER_WORKERS", 1)

    @property
    def MERMAID_MAX_SOURCE_CHARS(self) -> int:
        return _int("MERMAID_MAX_SOURCE_CHARS", 20000)

    @property
    def DOCUMENT_DIAGRAM_CACHE_SIZE(self) -> int:
        return _int("DOCUMENT_DIAGRAM_CACHE_SIZE", 256)

    @property
    def ENABLE_API_DOCS(self) -> bool:
        return _bool("ENABLE_API_DOCS", False)

    @property
    def EXECUTOR_UID(self) -> int:
        return _int("EXECUTOR_UID", 0)

    @property
    def GATEWAY_URL(self) -> str | None:
        return os.environ.get("GATEWAY_URL")

    @property
    def GRAPH_EXTRACTION_TIMEOUT_SECONDS(self) -> float:
        return _float("GRAPH_EXTRACTION_TIMEOUT_SECONDS", 120.0)

    @property
    def IS_TESTING(self) -> bool:
        return _bool("IS_TESTING", False)

    @property
    def KEYCLOAK_AGENT_SERVICE_AUDIENCE(self) -> str | None:
        return os.environ.get("KEYCLOAK_AGENT_SERVICE_AUDIENCE")

    @property
    def KEYCLOAK_AGENT_SERVICE_CLIENT_ID(self) -> str:
        return _required("KEYCLOAK_AGENT_SERVICE_CLIENT_ID")

    @property
    def KEYCLOAK_RAG_SERVICE_CLIENT_ID(self) -> str:
        return _required("KEYCLOAK_RAG_SERVICE_CLIENT_ID")

    @property
    def KEYCLOAK_TOOLS_SERVICE_CLIENT_ID(self) -> str:
        return _required("KEYCLOAK_TOOLS_SERVICE_CLIENT_ID")

    @property
    def KEYCLOAK_AGENT_SERVICE_CLIENT_SECRET(self) -> str | None:
        return os.environ.get("KEYCLOAK_AGENT_SERVICE_CLIENT_SECRET")

    # How long a fetched JWKS may be reused, passed to PyJWKClient as its
    # `lifespan`. 300s is PyJWT's own default.
    @property
    def KEYCLOAK_JWKS_CACHE_TTL_SECONDS(self) -> int:
        return _int("KEYCLOAK_JWKS_CACHE_TTL_SECONDS", 300)

    @property
    def LLAMA_GUARD_MODEL(self) -> str:
        return os.environ.get("LLAMA_GUARD_MODEL", "llama3.1:8b")

    @property
    def LLM_ANTHROPIC_THINKING_BUDGET_TOKENS(self) -> int:
        return _int("LLM_ANTHROPIC_THINKING_BUDGET_TOKENS", 8000)

    @property
    def LLM_AZURE_API_VERSION(self) -> str:
        return os.environ.get("LLM_AZURE_API_VERSION", "2024-10-21")

    @property
    def LLM_BEDROCK_CONNECT_TIMEOUT_SECONDS(self) -> int:
        return _int("LLM_BEDROCK_CONNECT_TIMEOUT_SECONDS", 10)

    @property
    def LLM_BEDROCK_READ_TIMEOUT_SECONDS(self) -> int:
        return _int("LLM_BEDROCK_READ_TIMEOUT_SECONDS", 60)

    @property
    def LLM_EXTRA_REASONING_MODEL_PREFIXES(self) -> str:
        return os.environ.get("LLM_EXTRA_REASONING_MODEL_PREFIXES", "")

    @property
    def LLM_GEMINI_THINKING_BUDGET_TOKENS(self) -> int:
        return _int("LLM_GEMINI_THINKING_BUDGET_TOKENS", 8000)

    @property
    def LLM_MAX_RETRIES(self) -> int:
        return _int("LLM_MAX_RETRIES", 2)

    @property
    def LLM_MISTRAL_BASE_URL(self) -> str:
        return os.environ.get("LLM_MISTRAL_BASE_URL", "https://api.mistral.ai/v1")

    @property
    def LLM_OPENAI_REASONING_EFFORT(self) -> str:
        return os.environ.get("LLM_OPENAI_REASONING_EFFORT", "medium")

    @property
    def LLM_REQUEST_TIMEOUT(self) -> float:
        return _float("LLM_REQUEST_TIMEOUT", 600.0)

    # Long-term memory tunables (agent-service memory/long_term.py).
    @property
    def LTM_CONTEXT_MAX_CHARS(self) -> int:
        return _int("LTM_CONTEXT_MAX_CHARS", 6000)

    @property
    def LTM_EXTRACTION_TIMEOUT_SECONDS(self) -> float:
        return _float("LTM_EXTRACTION_TIMEOUT_SECONDS", 30.0)

    @property
    def LTM_EXTRACTION_WINDOW_MESSAGES(self) -> int:
        return _int("LTM_EXTRACTION_WINDOW_MESSAGES", 6)

    @property
    def LTM_MAX_CONCURRENT_EXTRACTIONS(self) -> int:
        return _int("LTM_MAX_CONCURRENT_EXTRACTIONS", 5)

    @property
    def MCP_ALLOW_PRIVATE_URLS(self) -> bool:
        return _bool("MCP_ALLOW_PRIVATE_URLS", False)

    @property
    def MCP_GITHUB_SERVER_URL(self) -> str:
        return os.environ.get("MCP_GITHUB_SERVER_URL", "https://api.githubcopilot.com/mcp/")

    @property
    def MCP_HOST(self) -> str | None:
        return os.environ.get("MCP_HOST")

    @property
    def MCP_PUBLIC_BASE_URL(self) -> str:
        return os.environ.get("MCP_PUBLIC_BASE_URL") or f"http://{self.MCP_HOST}:{self.TOOLS_SERVICE_PORT}/mcp"

    # Model fact extraction runs on when it should differ from the
    # conversation's model; unset extracts with the conversation's own model.
    @property
    def MEMORY_EXTRACTION_MODEL(self) -> str | None:
        value = os.environ.get("MEMORY_EXTRACTION_MODEL", "").strip()
        return value or None

    # Per-user cap on stored long-term-memory facts (user-service).
    @property
    def MEMORY_MAX_FACTS(self) -> int:
        return _int("MEMORY_MAX_FACTS", 50)

    @property
    def OPEN_URL_PLAYWRIGHT_FALLBACK_ENABLED(self) -> bool:
        return _bool("OPEN_URL_PLAYWRIGHT_FALLBACK_ENABLED", False)

    @property
    def POSTGRES_APPLICATION_NAME(self) -> str:
        return os.environ.get("POSTGRES_APPLICATION_NAME", "agent-service")

    @property
    def POSTGRES_COMMAND_TIMEOUT_SECONDS(self) -> float:
        return _float("POSTGRES_COMMAND_TIMEOUT_SECONDS", 30.0)

    @property
    def POSTGRES_MAX_CONNECTIONS_PER_POOL(self) -> int:
        return _int("POSTGRES_MAX_CONNECTIONS_PER_POOL", 20)

    @property
    def POSTGRES_MAX_OVERFLOW(self) -> int:
        return _int("POSTGRES_MAX_OVERFLOW", 5)

    @property
    def POSTGRES_MIN_CONNECTIONS_PER_POOL(self) -> int:
        return _int("POSTGRES_MIN_CONNECTIONS_PER_POOL", 2)

    @property
    def POSTGRES_POOL_RECONNECT_TIMEOUT_SECONDS(self) -> float:
        return _float("POSTGRES_POOL_RECONNECT_TIMEOUT_SECONDS", 300.0)

    @property
    def POSTGRES_POOL_RECYCLE_SECONDS(self) -> int:
        return _int("POSTGRES_POOL_RECYCLE_SECONDS", 1800)

    @property
    def POSTGRES_POOL_SIZE(self) -> int:
        return _int("POSTGRES_POOL_SIZE", 10)

    @property
    def POSTGRES_POOL_TIMEOUT_SECONDS(self) -> float:
        return _float("POSTGRES_POOL_TIMEOUT_SECONDS", 30.0)

    @property
    def POSTGRES_POOL_USE_LIFO(self) -> bool:
        return _bool("POSTGRES_POOL_USE_LIFO", True)

    # Inactivity TTL for real (non-playground) conversation threads. 0 disables
    # production retention: deleting real chat history is opt-in.
    @property
    def PRODUCTION_RETENTION_DAYS(self) -> int:
        return _int("PRODUCTION_RETENTION_DAYS", 0)

    # No default: agent-service falls back to configs/resilience.yaml, and
    # user-service to its own client default.
    @property
    def RAG_HTTP_TIMEOUT_SECONDS(self) -> float | None:
        return _float("RAG_HTTP_TIMEOUT_SECONDS")

    @property
    def SERVICE_HOST(self) -> str:
        return os.environ.get("SERVICE_HOST", "0.0.0.0")

    @property
    def SERVICE_NAME(self) -> str:
        return os.environ.get("SERVICE_NAME", "user-service")

    @property
    def STREAM_HEARTBEAT_SECONDS(self) -> float:
        return _float("STREAM_HEARTBEAT_SECONDS", 15.0)

    @property
    def CHAT_RUN_REPLAY_TTL_SECONDS(self) -> int:
        return _int("CHAT_RUN_REPLAY_TTL_SECONDS", 600)

    @property
    def CHAT_RUN_LEASE_TTL_SECONDS(self) -> float:
        return _float("CHAT_RUN_LEASE_TTL_SECONDS", 10.0)

    @property
    def CHAT_RUN_HEARTBEAT_SECONDS(self) -> float:
        return _float("CHAT_RUN_HEARTBEAT_SECONDS", 2.0)

    @property
    def CHAT_RUN_MAX_EVENTS(self) -> int:
        return _int("CHAT_RUN_MAX_EVENTS", 50000)

    @property
    def CHAT_RUN_CANCEL_GRACE_SECONDS(self) -> float:
        return _float("CHAT_RUN_CANCEL_GRACE_SECONDS", 5.0)

    @property
    def CHAT_RUN_SHUTDOWN_GRACE_SECONDS(self) -> float:
        return _float("CHAT_RUN_SHUTDOWN_GRACE_SECONDS", 20.0)

    @property
    def CHAT_RUN_REAPER_INTERVAL_SECONDS(self) -> float:
        return _float("CHAT_RUN_REAPER_INTERVAL_SECONDS", 10.0)

    @property
    def CHAT_RUN_MAX_DURATION_SECONDS(self) -> int:
        return _int("CHAT_RUN_MAX_DURATION_SECONDS", 3600)

    @property
    def USER_PERMISSION_CACHE_TTL_SECONDS(self) -> float:
        return _float("USER_PERMISSION_CACHE_TTL_SECONDS", 30.0)

    @property
    def WORKSPACE_DIR(self) -> str:
        return os.environ.get("WORKSPACE_DIR", "/workspace")


env = _env = ConfigManager()
