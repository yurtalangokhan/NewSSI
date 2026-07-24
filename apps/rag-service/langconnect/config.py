import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from langchain_core.embeddings import Embeddings
from starlette.config import Config

env = Config()

IS_TESTING = env("IS_TESTING", cast=str, default="").lower() == "true"

# Simple Auth configuration
VALID_API_KEYS = env("VALID_API_KEYS", cast=str, default="")


def _require_env(mapping: Mapping[str, Any], name: str) -> str:
    value = str(mapping.get(name, "")).strip()
    if not value:
        raise ValueError(f"Required environment variable {name} is not set")
    return value


@dataclass(frozen=True)
class Settings:
    postgres_host: str
    postgres_port: int
    postgres_user: str
    postgres_password: str
    postgres_db: str
    user_service_url: str
    internal_service_token: str
    keycloak_client_secret: str
    keycloak_issuer_url: str
    keycloak_audience: str

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "Settings":
        """Build settings from an explicit environment mapping."""
        return cls(
            postgres_host=_require_env(mapping, "POSTGRES_HOST"),
            postgres_port=int(_require_env(mapping, "POSTGRES_PORT")),
            postgres_user=_require_env(mapping, "POSTGRES_USER"),
            postgres_password=_require_env(mapping, "POSTGRES_PASSWORD"),
            postgres_db=_require_env(mapping, "POSTGRES_DB"),
            user_service_url=_require_env(mapping, "USER_SERVICE_URL"),
            internal_service_token=_require_env(mapping, "INTERNAL_SERVICE_TOKEN"),
            keycloak_client_secret=_require_env(mapping, "KEYCLOAK_CLIENT_SECRET"),
            keycloak_issuer_url=_require_env(mapping, "KEYCLOAK_ISSUER_URL"),
            keycloak_audience=_require_env(mapping, "KEYCLOAK_AUDIENCE"),
        )

    @property
    def postgres_config(self) -> dict[str, Any]:
        """Return Postgres connection settings in legacy dict form."""
        return {
            "host": self.postgres_host,
            "port": self.postgres_port,
            "user": self.postgres_user,
            "password": self.postgres_password,
            "database": self.postgres_db,
        }


def parse_valid_api_keys(raw_value: str | None = None) -> set[str]:
    """Parse configured API keys from a comma-separated string."""
    value = VALID_API_KEYS if raw_value is None else raw_value
    return {key.strip() for key in value.split(",") if key.strip()}

# Keycloak JWKS-based token validation
KEYCLOAK_ENABLED = env("KEYCLOAK_ENABLED", cast=bool, default=False)
KEYCLOAK_ISSUER_URL = env("KEYCLOAK_ISSUER_URL", cast=str, default="")
KEYCLOAK_AUDIENCE = env("KEYCLOAK_AUDIENCE", cast=str, default="")
KEYCLOAK_CLIENT_ID = env("KEYCLOAK_CLIENT_ID", cast=str, default="agenticai-web")
KEYCLOAK_CLIENT_SECRET = env("KEYCLOAK_CLIENT_SECRET", cast=str, default="")
KEYCLOAK_TOKEN_LEEWAY_SECONDS = env(
    "KEYCLOAK_TOKEN_LEEWAY_SECONDS", cast=int, default=120
)
INTERNAL_SERVICE_TOKEN = env("INTERNAL_SERVICE_TOKEN", cast=str, default="")
USER_SERVICE_URL = env("USER_SERVICE_URL", cast=str, default="http://user-service:8090")
USER_PERMISSION_CACHE_TTL_SECONDS = env(
    "USER_PERMISSION_CACHE_TTL_SECONDS", cast=float, default=30.0
)

# Embedding configuration
EMBEDDING_PROVIDER = env("EMBEDDING_PROVIDER", cast=str, default="ollama")
OLLAMA_BASE_URL = env(
    "OLLAMA_BASE_URL", cast=str, default="http://host.docker.internal:11434"
)
OLLAMA_EMBED_MODEL = env("OLLAMA_EMBED_MODEL", cast=str, default="nomic-embed-text")


def get_embeddings() -> Embeddings:
    """Get the embeddings instance based on the environment."""
    if IS_TESTING:
        from langchain_core.embeddings import DeterministicFakeEmbedding

        return DeterministicFakeEmbedding(size=512)

    provider = EMBEDDING_PROVIDER.lower()

    if provider == "ollama":
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(model=OLLAMA_EMBED_MODEL, base_url=OLLAMA_BASE_URL)

    # Default to OpenAI
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings()


DEFAULT_EMBEDDINGS = get_embeddings()
DEFAULT_COLLECTION_NAME = "default_collection"


# Vector DB provider selection
VECTOR_DB_PROVIDER = env("VECTOR_DB_PROVIDER", cast=str, default="milvus")

# Database configuration (Postgres — used for collection metadata)
POSTGRES_HOST = env("POSTGRES_HOST", cast=str, default="localhost")
POSTGRES_PORT = env("POSTGRES_PORT", cast=int, default="5432")
POSTGRES_USER = env("POSTGRES_USER", cast=str, default="langchain")
POSTGRES_PASSWORD = env("POSTGRES_PASSWORD", cast=str, default="langchain")
POSTGRES_DB = env("POSTGRES_DB", cast=str, default="langchain_test")

# Milvus configuration
MILVUS_HOST = env("MILVUS_HOST", cast=str, default="localhost")
MILVUS_PORT = env("MILVUS_PORT", cast=int, default="9765")
MILVUS_USER = env("MILVUS_USER", cast=str, default="")
MILVUS_PASSWORD = env("MILVUS_PASSWORD", cast=str, default="")

# Read allowed origins from environment variable
ALLOW_ORIGINS_JSON = env("ALLOW_ORIGINS", cast=str, default="")


def parse_allowed_origins(raw_value: str | None) -> list[str]:
    """Parse CORS origins from JSON, shell-sourced, or comma-separated env values."""
    if not raw_value:
        return ["http://localhost:3000"]

    normalized = raw_value.strip()
    if not normalized:
        return ["http://localhost:3000"]

    try:
        parsed = json.loads(normalized)
        if isinstance(parsed, str):
            return [parsed]
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass

    # Shell sourcing can strip quotes from values like ["*"] -> [*]
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]

    parts = [part.strip().strip("\"'") for part in normalized.split(",")]
    parsed_parts = [part for part in parts if part]
    return parsed_parts or ["http://localhost:3000"]


# Neo4j configuration
NEO4J_URI = env("NEO4J_URI", cast=str, default="bolt://localhost:7687")
NEO4J_USERNAME = env("NEO4J_USERNAME", cast=str, default="neo4j")
NEO4J_PASSWORD = env("NEO4J_PASSWORD", cast=str, default="neo4j123")

# Idempotency / Redis configuration
REDIS_HOST = env("REDIS_HOST", cast=str, default="localhost")
REDIS_PORT = env("REDIS_PORT", cast=int, default=6379)
REDIS_DB = env("REDIS_DB", cast=int, default=0)
REDIS_PASSWORD = env("REDIS_PASSWORD", cast=str, default="")
IDEMPOTENCY_TTL = env("IDEMPOTENCY_TTL", cast=int, default=86400)
IDEMPOTENCY_ENABLED = env("IDEMPOTENCY_ENABLED", cast=bool, default=True)

ALLOWED_ORIGINS = parse_allowed_origins(ALLOW_ORIGINS_JSON)
if ALLOW_ORIGINS_JSON:
    print(f"ALLOW_ORIGINS environment variable set to: {ALLOW_ORIGINS_JSON}")
else:
    print("ALLOW_ORIGINS environment variable not set.")
