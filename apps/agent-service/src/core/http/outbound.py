"""One pooled transport for every outbound HTTP call.

Before this module, 37 call sites built ``httpx.AsyncClient(...)`` per request.
Each construction opens a fresh TCP connection (and TLS handshake), keeps no
keep-alive pool, has no connection ceiling, and costs an ``aclose()`` round trip
before the response is even used. The platform already ships the fix —
``security.get_shared_client``, a process-wide registry of pooled clients that
``close_all()`` drains on shutdown — but exactly one module used it.

Two entry points:

* :func:`get_client` — the shared pooled client for a dependency, for callers
  that need streaming or a bespoke response flow.
* :func:`request` — the common path, which adds the per-request timeout, the
  circuit breaker and the retry budget from ``configs/resilience.yaml``, and
  maps an open circuit to the platform's typed dependency error.

Timeouts are passed **per request**, never at construction: one client per
dependency has to serve call sites with different budgets, and
``get_shared_client`` only honours kwargs the first time a name is requested.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
from observability import outbound_headers
from security import (
    CircuitBreakerOpenError,
    get_circuit_breaker,
    get_shared_client,
    get_shared_sync_client,
    retry_for,
    timeout_for,
)

from core.exceptions import (
    DependencyResponseError,
    DependencyUnavailableError,
    from_httpx_error,
)
from core.observability.logger import get_logger

logger = get_logger(__name__)

# These names MUST match keys under `dependencies:` in configs/resilience.yaml.
# Adding one here without adding it there silently falls back to `defaults`.
USER_SERVICE = "user-service"
RAG_SERVICE = "rag-service"
# Connector ingestion into rag-service: minutes-long requests with their own
# pool, budget and breaker, so a slow ingest cannot open the circuit that chat
# retrieval shares (see configs/resilience.yaml).
RAG_SERVICE_INGEST = "rag-service-ingest"
TOOLS_SERVICE = "tools-service"
KEYCLOAK = "keycloak"
OLLAMA = "ollama"
VLLM = "vllm"
MINIO = "minio"
# User-supplied addresses (a provider base URL, a page to crawl). There is no
# shared budget to trip, so the caller decides the timeout and the breaker is
# skipped: one hostile host must not open a circuit for every other one.
EXTERNAL = "external"

# The dependencies whose calls are wrapped in a breaker. `external` is absent by
# design; `ollama` and `vllm` are local runtimes that are expected to be up, and
# a breaker there would turn a brief restart into a longer outage.
BREAKER_EXEMPT = frozenset({EXTERNAL})


def get_client(dependency: str) -> httpx.AsyncClient:
    """The shared, pooled ``httpx.AsyncClient`` for *dependency*."""
    return get_shared_client(dependency)


def get_sync_client(dependency: str) -> httpx.Client:
    """The shared, pooled ``httpx.Client`` for *dependency*.

    Companion to :func:`get_client` for blocking callers. Module-level
    ``httpx.get`` / ``httpx.post`` build and discard a client — and therefore a
    connection pool — on every call; this reuses one per dependency for the life
    of the process.

    Timeouts are passed per request here too, so a single client serves call
    sites with different budgets.
    """
    return get_shared_sync_client(dependency)


def resolve_timeout(
    dependency: str,
    timeout: float | httpx.Timeout | None = None,
) -> float | httpx.Timeout:
    """Per-request timeout: the explicit value, else the dependency's policy."""
    if timeout is not None:
        return timeout
    return timeout_for(dependency)


def _with_correlation(headers: Mapping[str, str] | None) -> dict[str, str]:
    """Merge the request's correlation id into the outbound headers.

    Every call this module sends continues the correlation chain the request
    arrived with, so one identifier spans every service a request touches. A
    caller's explicit header wins: a call site that deliberately sends a
    different correlation id is not overruled.
    """
    merged = dict(outbound_headers())
    if headers:
        merged.update(headers)
    return merged


async def request(
    dependency: str,
    method: str,
    url: str,
    *,
    timeout: float | httpx.Timeout | None = None,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    json: Any | None = None,
    data: Any | None = None,
    content: Any | None = None,
    follow_redirects: bool | None = None,
) -> httpx.Response:
    """Send one request through the shared client, with the dependency's policy.

    Retry sits inside the breaker, so a burst of transient failures counts as a
    single failure against the circuit and the retry budget cannot trip it on
    its own. An open circuit becomes
    :class:`~error_contract.DependencyUnavailableError` — a typed 503 — instead
    of leaking a resilience-package exception into the route layer.
    """
    request_timeout = resolve_timeout(dependency, timeout)

    @retry_for(dependency)
    async def _send() -> httpx.Response:
        return await get_client(dependency).request(
            method,
            url,
            headers=_with_correlation(headers),
            params=params,
            json=json,
            data=data,
            content=content,
            timeout=request_timeout,
            follow_redirects=follow_redirects if follow_redirects is not None else True,
        )

    try:
        if dependency in BREAKER_EXEMPT:
            return await _send()
        async with get_circuit_breaker(dependency):
            return await _send()
    except CircuitBreakerOpenError as exc:
        logger.warning(
            "Circuit breaker open for dependency %s",
            dependency,
            extra={
                "event": "outbound.circuit_open",
                "dependency": dependency,
                "reset_in_seconds": exc.reset_in_seconds,
            },
        )
        raise DependencyUnavailableError(
            code=f"{dependency}.circuit_open",
            details={"reset_in_seconds": exc.reset_in_seconds},
            retry_after=int(exc.reset_in_seconds) or 1,
        ) from exc
    except httpx.HTTPError as exc:
        raise from_httpx_error(exc) from exc


async def request_json(
    dependency: str,
    method: str,
    url: str,
    *,
    timeout: float | httpx.Timeout | None = None,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    json: Any | None = None,
    data: Any | None = None,
    content: Any | None = None,
    follow_redirects: bool | None = None,
) -> Any:
    """:func:`request` plus ``raise_for_status`` and JSON decoding."""
    response = await request(
        dependency,
        method,
        url,
        timeout=timeout,
        headers=headers,
        params=params,
        json=json,
        data=data,
        content=content,
        follow_redirects=follow_redirects,
    )
    try:
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        raise from_httpx_error(exc) from exc
    except ValueError as exc:
        raise DependencyResponseError() from exc


__all__ = [
    "BREAKER_EXEMPT",
    "EXTERNAL",
    "KEYCLOAK",
    "MINIO",
    "OLLAMA",
    "RAG_SERVICE",
    "RAG_SERVICE_INGEST",
    "TOOLS_SERVICE",
    "USER_SERVICE",
    "VLLM",
    "get_client",
    "get_sync_client",
    "request",
    "request_json",
    "resolve_timeout",
]
