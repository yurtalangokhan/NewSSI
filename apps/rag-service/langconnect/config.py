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


# Database configuration
POSTGRES_HOST = env("POSTGRES_HOST", cast=str, default="localhost")
POSTGRES_PORT = env("POSTGRES_PORT", cast=int, default="5432")
POSTGRES_USER = env("POSTGRES_USER", cast=str, default="langchain")
POSTGRES_PASSWORD = env("POSTGRES_PASSWORD", cast=str, default="langchain")
POSTGRES_DB = env("POSTGRES_DB", cast=str, default="langchain_test")

# Read allowed origins from environment variable
ALLOW_ORIGINS_JSON = env("ALLOW_ORIGINS", cast=str, default="")

# Neo4j configuration
NEO4J_URI = env("NEO4J_URI", cast=str, default="bolt://localhost:7687")
NEO4J_USERNAME = env("NEO4J_USERNAME", cast=str, default="neo4j")
NEO4J_PASSWORD = env("NEO4J_PASSWORD", cast=str, default="neo4j123")

if ALLOW_ORIGINS_JSON:
    ALLOWED_ORIGINS = json.loads(ALLOW_ORIGINS_JSON.strip())
    print(f"ALLOW_ORIGINS environment variable set to: {ALLOW_ORIGINS_JSON}")
else:
    ALLOWED_ORIGINS = "http://localhost:3000"
    print("ALLOW_ORIGINS environment variable not set.")
