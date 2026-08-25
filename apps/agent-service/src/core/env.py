"""
Centralized environment variable management.

This module provides a single source for all environment variables.
All other modules should import from here instead of reading os.environ directly.

Architecture:
- This is the ONLY module that reads from os.environ directly
- Other modules import from core.env to access configuration
- Settings class handles validation and defaults
"""

import os
from functools import cache
from typing import Any

from dotenv import load_dotenv

load_dotenv()


class Env:
    """
    Centralized environment variable access.

    Usage:
        from core.env import env

        # Get required env var
        postgres_host = env.POSTGRES_HOST

        # Get optional env var with default
        port = env.OLLAMA_BASE_URL or "http://localhost:11434"

        # Check if feature is enabled
        if env.USE_FAKE_MODEL:
            ...
    """

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    def __getattr__(self, name: str) -> Any:
        if name not in self._cache:
            self._cache[name] = os.environ.get(name)
        return self._cache[name]

    def get(self, key: str, default: Any = None) -> Any:
        """Get env var with default."""
        return os.environ.get(key, default)

    def require(self, key: str) -> str:
        """Get required env var, raises if not found."""
        value = os.environ.get(key)
        if value is None:
            raise ValueError(f"Required environment variable {key} is not set")
        return value

    @property
    def POSTGRES_USER(self) -> str | None:
        return os.environ.get("POSTGRES_USER")

    @property
    def POSTGRES_PASSWORD(self) -> str | None:
        return os.environ.get("POSTGRES_PASSWORD")

    @property
    def POSTGRES_HOST(self) -> str | None:
        return os.environ.get("POSTGRES_HOST")

    @property
    def POSTGRES_PORT(self) -> int | None:
        port = os.environ.get("POSTGRES_PORT")
        return int(port) if port else None

    @property
    def POSTGRES_DB(self) -> str | None:
        return os.environ.get("POSTGRES_DB")

    @property
    def DATABASE_TYPE(self) -> str:
        return os.environ.get("DATABASE_TYPE", "sqlite")

    @property
    def SQLITE_DB_PATH(self) -> str:
        return os.environ.get("SQLITE_DB_PATH", "checkpoints.db")

    @property
    def HOST(self) -> str:
        return os.environ.get("HOST", "0.0.0.0")

    @property
    def PORT(self) -> int:
        return int(os.environ.get("PORT", "8080"))

    @property
    def AGENT_URL(self) -> str | None:
        return os.environ.get("AGENT_URL")

    @property
    def LOG_LEVEL(self) -> str:
        return os.environ.get("LOG_LEVEL", "INFO")

    @property
    def MODE(self) -> str | None:
        return os.environ.get("MODE")

    @property
    def AUTH_SECRET(self) -> str | None:
        return os.environ.get("AUTH_SECRET")

    @property
    def KEYCLOAK_ENABLED(self) -> bool:
        return os.environ.get("KEYCLOAK_ENABLED", "false").lower() == "true"

    @property
    def KEYCLOAK_ISSUER_URL(self) -> str | None:
        return os.environ.get("KEYCLOAK_ISSUER_URL")

    @property
    def KEYCLOAK_AUDIENCE(self) -> str | None:
        return os.environ.get("KEYCLOAK_AUDIENCE")

    @property
    def KEYCLOAK_TOKEN_LEEWAY_SECONDS(self) -> int:
        return int(os.environ.get("KEYCLOAK_TOKEN_LEEWAY_SECONDS", "120"))

    @property
    def KEYCLOAK_CLIENT_SECRET(self) -> str | None:
        return os.environ.get("KEYCLOAK_CLIENT_SECRET")

    @property
    def OLLAMA_BASE_URL(self) -> str | None:
        return os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_URL")

    @property
    def OLLAMA_MODEL(self) -> str | None:
        return os.environ.get("OLLAMA_MODEL")

    @property
    def OLLAMA_EMBED_MODEL(self) -> str | None:
        return os.environ.get("OLLAMA_EMBED_MODEL")

    @property
    def DEFAULT_MODEL(self) -> str:
        return os.environ.get("DEFAULT_MODEL") or os.environ.get("OLLAMA_MODEL") or "llama3.1:8b"

    @property
    def EMBEDDING_PROVIDER(self) -> str:
        return os.environ.get("EMBEDDING_PROVIDER", "ollama")

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
    def USE_FAKE_MODEL(self) -> bool:
        return os.environ.get("USE_FAKE_MODEL", "false").lower() == "true"

    @property
    def MCP_SERVER_URL(self) -> str:
        return os.environ.get("MCP_SERVER_URL", "http://localhost:8003/mcp")

    @property
    def TOOLS_SERVICE_URL(self) -> str | None:
        return os.environ.get("TOOLS_SERVICE_URL")

    @property
    def USER_SERVICE_URL(self) -> str | None:
        return os.environ.get("USER_SERVICE_URL")

    @property
    def RAG_SERVICE_API_URL(self) -> str | None:
        return os.environ.get("RAG_SERVICE_API_URL")

    @property
    def RAG_API_URL(self) -> str | None:
        return os.environ.get("RAG_API_URL")

    @property
    def GITHUB_PAT(self) -> str | None:
        return os.environ.get("GITHUB_PAT")

    @property
    def LANGFUSE_TRACING(self) -> bool:
        return os.environ.get("LANGFUSE_TRACING", "false").lower() == "true"

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
        return os.environ.get("LANGCHAIN_TRACING_V2", "false").lower() == "true"

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
    def NEO4J_URI(self) -> str:
        return os.environ.get("NEO4J_URI", "bolt://neo4j:7687")

    @property
    def NEO4J_USERNAME(self) -> str:
        return os.environ.get("NEO4J_USERNAME", "neo4j")

    @property
    def NEO4J_PASSWORD(self) -> str:
        return os.environ.get("NEO4J_PASSWORD", "neo4j123")

    @property
    def MILVUS_HOST(self) -> str:
        return os.environ.get("MILVUS_HOST", "localhost")

    @property
    def MILVUS_PORT(self) -> str:
        return os.environ.get("MILVUS_PORT", "9765")

    @property
    def MILVUS_USER(self) -> str:
        return os.environ.get("MILVUS_USER", "")

    @property
    def MILVUS_PASSWORD(self) -> str:
        return os.environ.get("MILVUS_PASSWORD", "")

    @property
    def GRACEFUL_SHUTDOWN_TIMEOUT(self) -> int:
        return int(os.environ.get("GRACEFUL_SHUTDOWN_TIMEOUT", "30"))

    @property
    def AIRBYTE_API_URL(self) -> str | None:
        return os.environ.get("AIRBYTE_API_URL")

    @property
    def AIRBYTE_DESTINATION_AGENT_TOKEN(self) -> str | None:
        return os.environ.get("AIRBYTE_DESTINATION_AGENT_TOKEN")

    @property
    def AIRBYTE_EMBED_BATCH_SIZE(self) -> int:
        return int(os.environ.get("AIRBYTE_EMBED_BATCH_SIZE", "200"))

    @property
    def AIRBYTE_SYNC_POLL_INTERVAL_SECONDS(self) -> int:
        return int(os.environ.get("AIRBYTE_SYNC_POLL_INTERVAL_SECONDS", "30"))

    @property
    def AIRBYTE_LOCAL_OUTPUT_PATH(self) -> str:
        return os.environ.get("AIRBYTE_LOCAL_OUTPUT_PATH", "/tmp/airbyte_local")

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
    def ENCRYPTION_KEY(self) -> str | None:
        return os.environ.get("ENCRYPTION_KEY")

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
        return int(os.environ.get("LOG_MAX_SIZE", str(10 * 1024 * 1024)))

    @property
    def LOG_BACKUP_COUNT(self) -> int:
        return int(os.environ.get("LOG_BACKUP_COUNT", "5"))


@cache
def get_env() -> Env:
    """Get singleton Env instance."""
    return Env()


env = get_env()
