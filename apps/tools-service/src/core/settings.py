"""Centralized runtime configuration for tools-service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cache

REQUIRED_ENV_NAMES = (
    "MCP_HOST",
    "MCP_PORT",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "USER_SERVICE_URL",
)


def optional_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        raise ValueError(f"Required environment variable {name} is not set")
    return value


@dataclass(frozen=True)
class Settings:
    mcp_host: str
    mcp_port: int
    postgres_host: str
    postgres_port: int
    postgres_user: str
    postgres_password: str
    postgres_db: str
    user_service_url: str
    agent_service_url: str
    rag_service_api_url: str
    redis_host: str
    redis_port: int
    redis_db: int
    redis_password: str
    idempotency_ttl: int
    idempotency_enabled: bool
    idempotency_enforce_required_keys: bool
    idempotency_lock_ttl: int
    idempotency_wait_timeout: float
    internal_service_token: str
    keycloak_issuer_url: str
    keycloak_audience: str
    keycloak_client_id: str
    keycloak_token_leeway_seconds: int
    mcp_public_base_url: str
    user_permission_cache_ttl_seconds: float
    valid_api_keys: str
    workspace_dir: str
    log_level: str
    connector_postgres_endpoints: str = "{}"

    @classmethod
    def required_env_names(cls) -> tuple[str, ...]:
        return REQUIRED_ENV_NAMES

    @classmethod
    def from_env(cls) -> Settings:
        mcp_host = require_env("MCP_HOST")
        mcp_port = int(require_env("MCP_PORT"))
        postgres_host = require_env("POSTGRES_HOST")
        postgres_port = int(require_env("POSTGRES_PORT"))
        postgres_user = require_env("POSTGRES_USER")
        postgres_password = require_env("POSTGRES_PASSWORD")
        postgres_db = require_env("POSTGRES_DB")
        user_service_url = require_env("USER_SERVICE_URL").rstrip("/")

        return cls(
            mcp_host=mcp_host,
            mcp_port=mcp_port,
            postgres_host=postgres_host,
            postgres_port=postgres_port,
            postgres_user=postgres_user,
            postgres_password=postgres_password,
            postgres_db=postgres_db,
            user_service_url=user_service_url,
            agent_service_url=optional_env("AGENT_SERVICE_URL").rstrip("/"),
            connector_postgres_endpoints=optional_env("CONNECTOR_POSTGRES_ENDPOINTS", "{}"),
            rag_service_api_url=optional_env("RAG_SERVICE_API_URL"),
            redis_host=optional_env("REDIS_HOST", "localhost"),
            redis_port=int(optional_env("REDIS_PORT", "6379")),
            redis_db=int(optional_env("REDIS_DB", "0")),
            redis_password=optional_env("REDIS_PASSWORD"),
            idempotency_ttl=int(optional_env("IDEMPOTENCY_TTL", "86400")),
            idempotency_enabled=optional_env("IDEMPOTENCY_ENABLED", "true").lower()
            in {"1", "true", "yes", "on"},
            idempotency_enforce_required_keys=optional_env(
                "IDEMPOTENCY_ENFORCE_REQUIRED_KEYS",
                "true",
            ).lower()
            in {"1", "true", "yes", "on"},
            idempotency_lock_ttl=int(optional_env("IDEMPOTENCY_LOCK_TTL", "10")),
            idempotency_wait_timeout=float(optional_env("IDEMPOTENCY_WAIT_TIMEOUT", "10.0")),
            internal_service_token=optional_env("INTERNAL_SERVICE_TOKEN").strip(),
            keycloak_issuer_url=optional_env("KEYCLOAK_ISSUER_URL").rstrip("/"),
            keycloak_audience=optional_env("KEYCLOAK_AUDIENCE"),
            keycloak_client_id=optional_env("KEYCLOAK_CLIENT_ID", "tools-service"),
            keycloak_token_leeway_seconds=int(optional_env("KEYCLOAK_TOKEN_LEEWAY_SECONDS", "120")),
            mcp_public_base_url=(
                optional_env("MCP_PUBLIC_BASE_URL")
                or optional_env("TOOLS_SERVICE_URL")
                or f"http://{mcp_host}:{mcp_port}/mcp"
            ),
            user_permission_cache_ttl_seconds=float(
                optional_env("USER_PERMISSION_CACHE_TTL_SECONDS", "30")
            ),
            valid_api_keys=optional_env("VALID_API_KEYS"),
            workspace_dir=optional_env("WORKSPACE_DIR", "/workspace"),
            log_level=optional_env("LOG_LEVEL", "INFO"),
        )

    @property
    def postgres_config(self) -> dict[str, str | int]:
        return {
            "user": self.postgres_user,
            "password": self.postgres_password,
            "host": self.postgres_host,
            "port": self.postgres_port,
            "database": self.postgres_db,
        }


@cache
def get_settings() -> Settings:
    return Settings.from_env()
