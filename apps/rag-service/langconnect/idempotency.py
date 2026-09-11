from types import SimpleNamespace
from typing import Protocol

from idempotency import (
    IdempotencyConfig,
    IdempotencyMode,
    IdempotencyPolicy,
    IdempotencyPolicyConfig,
)

from langconnect import config
from langconnect.api_versioning import API_PREFIX
from langconnect.idempotency_principal import extract_principal_from_jwt


class IdempotencySettings(Protocol):
    """Settings required to build idempotency middleware configuration."""

    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_DB: int
    REDIS_PASSWORD: str
    IDEMPOTENCY_TTL: int
    IDEMPOTENCY_ENABLED: bool
    IDEMPOTENCY_ENFORCE_REQUIRED_KEYS: bool
    IDEMPOTENCY_LOCK_TTL: int
    IDEMPOTENCY_WAIT_TIMEOUT: float


def current_idempotency_settings() -> SimpleNamespace:
    """Return idempotency settings from the active runtime config module."""
    return SimpleNamespace(
        REDIS_HOST=config.REDIS_HOST,
        REDIS_PORT=config.REDIS_PORT,
        REDIS_DB=config.REDIS_DB,
        REDIS_PASSWORD=config.REDIS_PASSWORD,
        IDEMPOTENCY_TTL=config.IDEMPOTENCY_TTL,
        IDEMPOTENCY_ENABLED=config.IDEMPOTENCY_ENABLED,
        IDEMPOTENCY_ENFORCE_REQUIRED_KEYS=config.IDEMPOTENCY_ENFORCE_REQUIRED_KEYS,
        IDEMPOTENCY_LOCK_TTL=config.IDEMPOTENCY_LOCK_TTL,
        IDEMPOTENCY_WAIT_TIMEOUT=config.IDEMPOTENCY_WAIT_TIMEOUT,
    )


def build_idempotency_config(
    settings: IdempotencySettings | None = None,
) -> IdempotencyConfig:
    """Build the shared middleware config for rag-service."""
    s = settings or current_idempotency_settings()
    return IdempotencyConfig(
        redis_host=s.REDIS_HOST,
        redis_port=s.REDIS_PORT,
        redis_db=s.REDIS_DB,
        redis_password=s.REDIS_PASSWORD,
        idempotency_ttl=s.IDEMPOTENCY_TTL,
        idempotency_enabled=s.IDEMPOTENCY_ENABLED,
        service_name="rag-service",
        enforce_required_keys=getattr(s, "IDEMPOTENCY_ENFORCE_REQUIRED_KEYS", False),
        lock_ttl=getattr(s, "IDEMPOTENCY_LOCK_TTL", 10),
        wait_timeout=getattr(s, "IDEMPOTENCY_WAIT_TIMEOUT", 10.0),
        principal_extractor=extract_principal_from_jwt,
        policy=build_idempotency_policy(),
    )


def build_idempotency_exclude_paths(api_prefix: str = API_PREFIX) -> set[str]:
    """Build public paths that bypass idempotency handling."""
    return {f"{api_prefix}/health", f"{api_prefix}/health/ready"}


def build_idempotency_policy(api_prefix: str = API_PREFIX) -> IdempotencyPolicyConfig:
    """Build route-level idempotency policy for rag-service."""
    domain_required = {
        "POST": [
            "/graph/build",
            "/graph/build/{collection_id}/pause",
            "/graph/build/{collection_id}/resume",
            "/graph/build/{collection_id}/stop",
            "/collections/{collection_id}/documents",
            "/collections/{collection_id}/documents/upload-jobs",
        ],
        "DELETE": [
            "/graph/collections/{collection_id}",
            "/collections/{collection_id}/force",
        ],
    }
    required_replay = {
        "POST": [
            "/collections",
        ],
        "PATCH": [
            "/collections/{collection_id}",
        ],
    }
    optional_replay = {
        "POST": [
            "/graph/search",
            "/collections/{collection_id}/documents/search",
            "/graph/cypher",
            "/retrieval",
        ],
        "DELETE": [
            "/collections/{collection_id}",
            "/collections/{collection_id}/documents/{document_id}",
        ],
    }

    return IdempotencyPolicyConfig(
        default_mode=IdempotencyMode.OPTIONAL_REPLAY,
        route_policies=[
            *build_route_policies(api_prefix, domain_required, IdempotencyMode.DOMAIN_REQUIRED),
            *build_route_policies(api_prefix, required_replay, IdempotencyMode.REQUIRED_REPLAY),
            *build_route_policies(api_prefix, optional_replay, IdempotencyMode.OPTIONAL_REPLAY),
        ],
    )


def build_route_policies(
    api_prefix: str,
    routes_by_method: dict[str, list[str]],
    mode: IdempotencyMode,
) -> list[IdempotencyPolicy]:
    """Expand method-to-path mappings into shared idempotency route policies."""
    return [
        IdempotencyPolicy(
            method=method,
            path=f"{api_prefix}{path}",
            mode=mode,
            # domain_required always enforces a key; other modes fall back to
            # the global enforce_required_keys flag (None).
            enforce_missing_key=(
                True if mode == IdempotencyMode.DOMAIN_REQUIRED else None
            ),
        )
        for method, paths in routes_by_method.items()
        for path in paths
    ]
