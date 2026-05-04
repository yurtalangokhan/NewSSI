import json
import os

from langchain_core.embeddings import Embeddings
from starlette.config import Config, undefined

env = Config()

IS_TESTING = env("IS_TESTING", cast=str, default="").lower() == "true"

# Simple Auth configuration
VALID_API_KEYS = env("VALID_API_KEYS", cast=str, default="")

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
    else:
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

    parts = [part.strip().strip('"\'') for part in normalized.split(",")]
    parsed_parts = [part for part in parts if part]
    return parsed_parts or ["http://localhost:3000"]

# Neo4j configuration
NEO4J_URI = env("NEO4J_URI", cast=str, default="bolt://localhost:7687")
NEO4J_USERNAME = env("NEO4J_USERNAME", cast=str, default="neo4j")
NEO4J_PASSWORD = env("NEO4J_PASSWORD", cast=str, default="neo4j123")

ALLOWED_ORIGINS = parse_allowed_origins(ALLOW_ORIGINS_JSON)
if ALLOW_ORIGINS_JSON:
    print(f"ALLOW_ORIGINS environment variable set to: {ALLOW_ORIGINS_JSON}")
else:
    print("ALLOW_ORIGINS environment variable not set.")
