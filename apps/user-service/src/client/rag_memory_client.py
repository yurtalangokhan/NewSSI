"""HTTP client for rag-service's user memory-facts semantic index.

Keeps the canonical Postgres fact store (this service) in sync with
rag-service's Milvus-backed embedding index: every create/update/delete in
UserMemoryService calls through here so agent-service's chat-turn semantic
recall sees the same facts. This module reports failures honestly (raises
on a non-2xx response or a transport error); the caller
(service.user_memory_service) is what decides these calls are best-effort
-- it runs them as tracked background tasks and logs failures rather than
letting a rag-service hiccup fail the user-facing CRUD request that
triggered the sync.
"""

from __future__ import annotations

from config_manager import env
from error_contract import (
    ApplicationError,
    ConfigurationError,
    DependencyResponseError,
    from_httpx_error,
    raise_for_httpx_response,
)
import httpx
from localization import get_locale
from pydantic import ValidationError

from src.core.response_models import ResponseModel

RAG_API_PREFIX = "/api/v1"
#: Used when ``RAG_HTTP_TIMEOUT_SECONDS`` is unset. The shared getter carries no
#: default because agent-service falls back to ``configs/resilience.yaml``.
DEFAULT_RAG_HTTP_TIMEOUT_SECONDS = 10.0


def _rag_base_url() -> str:
    """rag-service's root, without a trailing slash.

    Reads ``INTERNAL_RAG_SERVICE_API_URL``, the key agent-service uses for the
    identical backend. No hardcoded fallback: this used to default to
    ``http://localhost:8000``, unreachable from inside this container, so every
    sync to rag-service silently failed with an opaque connection error.
    """
    base_url = env.INTERNAL_RAG_SERVICE_API_URL
    if not base_url:
        raise ConfigurationError()
    return base_url


def _rag_url(path: str) -> str:
    """Absolute rag-service URL for `path` under the shared REST prefix."""
    return f"{_rag_base_url()}{RAG_API_PREFIX}{path}"


def _headers(user_id: str) -> dict[str, str]:
    return {
        "x-internal-token": env.INTERNAL_SERVICE_TOKEN or "",
        "x-user-id": user_id,
        "X-Language": get_locale(),
    }


def _build_client() -> httpx.AsyncClient:
    timeout = env.RAG_HTTP_TIMEOUT_SECONDS
    return httpx.AsyncClient(timeout=DEFAULT_RAG_HTTP_TIMEOUT_SECONDS if timeout is None else timeout)


async def upsert_fact(*, user_id: str, fact_id: str, content: str) -> None:
    """Embed and index one fact for `user_id` in rag-service's memory index."""
    await _request(
        "POST",
        "/memory/facts",
        user_id=user_id,
        json={"fact_id": fact_id, "content": content},
    )


async def delete_fact(*, user_id: str, fact_id: str) -> None:
    """Remove one fact's embedding from rag-service's memory index."""
    await _request("DELETE", f"/memory/facts/{fact_id}", user_id=user_id)


async def delete_all_facts(*, user_id: str) -> None:
    """Remove every fact embedding stored for `user_id`."""
    await _request("DELETE", "/memory/facts", user_id=user_id)


async def _request(method: str, path: str, *, user_id: str, json: dict | None = None) -> None:
    try:
        async with _build_client() as client:
            response = await client.request(
                method,
                _rag_url(path),
                json=json,
                headers=_headers(user_id),
            )
            try:
                payload = response.json()
            except ValueError as exc:
                raise_for_httpx_response(response)
                raise DependencyResponseError() from exc
            if not isinstance(payload, dict) or "statusCode" not in payload:
                raise_for_httpx_response(response)
                raise DependencyResponseError()
            try:
                result = ResponseModel[None].model_validate(payload, strict=True)
            except ValidationError as exc:
                raise DependencyResponseError() from exc
            if result.error is not None:
                if not 400 <= result.statusCode <= 599:
                    raise DependencyResponseError()
                raise ApplicationError(
                    status_code=result.statusCode,
                    code=result.error.code,
                    message=result.error.message,
                )
            raise_for_httpx_response(response)
            if not 200 <= result.statusCode < 300 or result.statusCode != response.status_code:
                raise DependencyResponseError()
    except httpx.HTTPError as error:
        raise from_httpx_error(error) from error
