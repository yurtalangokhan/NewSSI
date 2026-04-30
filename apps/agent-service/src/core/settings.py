from enum import StrEnum
from typing import Any

from pydantic import AliasChoices, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseType(StrEnum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"
    MONGO = "mongo"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def to_logging_level(self) -> int:
        import logging

        mapping = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.CRITICAL: logging.CRITICAL,
        }
        return mapping[self]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        validate_default=False,
    )

    MODE: str | None = None
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    GRACEFUL_SHUTDOWN_TIMEOUT: int = 30
    LOG_LEVEL: LogLevel = LogLevel.WARNING
    AUTH_SECRET: str | None = None
    KEYCLOAK_ENABLED: bool = False
    KEYCLOAK_ISSUER_URL: str | None = None
    KEYCLOAK_AUDIENCE: str | None = None

    OLLAMA_MODEL: str = "llama3.1:8b"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    DEFAULT_MODEL: str = "llama3.1:8b"
    EMBEDDING_PROVIDER: str = "ollama"

    COMPATIBLE_MODEL: str | None = None
    COMPATIBLE_API_KEY: str | None = None
    COMPATIBLE_BASE_URL: str | None = None

    MCP_SERVER_URL: str = Field(
        default="http://localhost:8002/mcp",
        validation_alias=AliasChoices("MCP_SERVER_URL", "TOOLS_SERVICE_URL"),
    )
    TOOLS_SERVICE_URL: str = Field(
        default="http://localhost:8002/mcp",
        validation_alias=AliasChoices("TOOLS_SERVICE_URL", "MCP_SERVER_URL"),
    )
    GITHUB_PAT: str | None = None

    LANGFUSE_TRACING: bool = False
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None

    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_PROJECT: str = "default"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGCHAIN_API_KEY: str | None = None

    DATABASE_TYPE: DatabaseType = DatabaseType.SQLITE
    SQLITE_DB_PATH: str = "checkpoints.db"

    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: str | None = None
    POSTGRES_HOST: str | None = None
    POSTGRES_PORT: int | None = None
    POSTGRES_DB: str | None = None
    POSTGRES_APPLICATION_NAME: str = "agent-service"
    POSTGRES_MIN_CONNECTIONS_PER_POOL: int = 2
    POSTGRES_MAX_CONNECTIONS_PER_POOL: int = 20

    MONGO_HOST: str | None = None
    MONGO_PORT: int | None = None
    MONGO_DB: str | None = None
    MONGO_USER: str | None = None
    MONGO_PASSWORD: str | None = None
    MONGO_AUTH_SOURCE: str | None = None

    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j123"

    VECTOR_DB_PROVIDER: str = "milvus"
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 9765
    MILVUS_USER: str = ""
    MILVUS_PASSWORD: str = ""

    AIRBYTE_API_URL: str | None = None
    AIRBYTE_LOCAL_OUTPUT_PATH: str = "/tmp/airbyte_local"

    @computed_field
    @property
    def BASE_URL(self) -> str:
        return f"http://{self.HOST}:{self.PORT}"

    @computed_field
    @property
    def AVAILABLE_MODELS(self) -> set[str]:
        """Available LLM models."""
        from schema.models import FakeModelName, OllamaModelName

        models = {m.value for m in OllamaModelName}
        models.add(FakeModelName.FAKE.value)
        return models

    def is_dev(self) -> bool:
        return self.MODE == "dev"


settings = Settings()
