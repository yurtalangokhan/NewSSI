# Copyright (c) 2026 Agentic AI Platform
import json
from types import SimpleNamespace
from typing import Protocol

from config_manager import env
from fastapi import Request, Response
from idempotency import (
    IdempotencyConfig,
    IdempotencyMiddleware,
    IdempotencyMode,
    IdempotencyPolicy,
    IdempotencyPolicyConfig,
)
from metrics import install_idempotency_recorder

from src.shared.api_versioning import API_PREFIX
from src.shared.idempotency_principal import extract_principal_from_jwt
from src.shared.response_models import ErrorModel, ResponseModel

#: Routes whose handler may run again for the same request, so a run that
#: failed (429, 5xx, or an exception) frees its key instead of closing it.
#: The records route replaces what an earlier run stored for a record: sending
#: a failed batch again cannot store it twice.
RERUN_AFTER_FAILURE_ROUTES = frozenset({("POST", "/datasources/{collection_id}/records")})


class IdempotencySettings(Protocol):
    """Settings required to build idempotency middleware configuration."""

    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_DB: int
    REDIS_PASSWORD: str
    IDEMPOTENCY_TTL: int
    IDEMPOTENCY_ENABLED: bool
    IDEMPOTENCY_LOCK_TTL: int
    IDEMPOTENCY_WAIT_TIMEOUT: float


def current_idempotency_settings() -> SimpleNamespace:
    """Return idempotency settings from the active runtime config module."""
    return SimpleNamespace(
        REDIS_HOST=env.REDIS_HOST,
        REDIS_PORT=env.REDIS_PORT,
        REDIS_DB=env.REDIS_DB,
        REDIS_PASSWORD=env.REDIS_PASSWORD,
        IDEMPOTENCY_TTL=env.IDEMPOTENCY_TTL,
        IDEMPOTENCY_ENABLED=env.IDEMPOTENCY_ENABLED,
        IDEMPOTENCY_LOCK_TTL=env.IDEMPOTENCY_LOCK_TTL,
        IDEMPOTENCY_WAIT_TIMEOUT=env.IDEMPOTENCY_WAIT_TIMEOUT,
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
        lock_ttl=s.IDEMPOTENCY_LOCK_TTL,
        wait_timeout=s.IDEMPOTENCY_WAIT_TIMEOUT,
        service_name="rag-service",
        decision_recorder=install_idempotency_recorder("rag-service"),
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
            "/datasources/{collection_id}/records",
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
            # Retiring the other runs of a collection is idempotent by itself: a
            # key only lets the same end-of-sync call replay its answer.
            "/datasources/{collection_id}/records/retire",
            "/graph/search",
            "/collections/{collection_id}/documents/search",
            "/graph/cypher",
            "/retrieval",
            "/search",
            "/search/graph/neighborhood",
            # Memory writes are idempotent on (user_id, fact_id) by
            # construction, and user-service calls them without a key, so
            # requiring one would reject every real write. Search is a read
            # dressed as POST because the query travels in the body.
            "/memory/facts",
            "/memory/search",
        ],
        "DELETE": [
            "/collections/{collection_id}",
            "/collections/{collection_id}/documents/{document_id}",
            # Dropping a datasource's table is idempotent by itself: a repeat
            # finds no table; a key only replays the answer.
            "/datasources/{collection_id}/records",
            "/memory/facts",
            "/memory/facts/{fact_id}",
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
            enforce_missing_key=(True if mode == IdempotencyMode.DOMAIN_REQUIRED else None),
            rerun_after_failure=(method, path) in RERUN_AFTER_FAILURE_ROUTES,
        )
        for method, paths in routes_by_method.items()
        for path in paths
    ]


class RagResponseIdempotencyMiddleware(IdempotencyMiddleware):
    """Retain idempotency policy and headers with service-local JSON errors."""

    @staticmethod
    def _error_response(status_code: int, code: str, message: str, *, request: Request | None = None) -> Response:
        original = IdempotencyMiddleware._error_response(status_code, code, message, request=request)
        error = json.loads(original.body)["error"]
        model = ResponseModel[None](
            statusCode=status_code,
            message=error["message"],
            error=ErrorModel(code=error["code"], message=error["message"]),
        )
        headers = dict(original.headers)
        headers.pop("content-length", None)
        return Response(
            model.model_dump_json(),
            status_code=status_code,
            headers=headers,
            media_type="application/json",
        )
