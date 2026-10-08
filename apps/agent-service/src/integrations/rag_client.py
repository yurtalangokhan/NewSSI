"""Typed client for agent-service -> rag-service calls.

`rag_http` owns the transport decisions (base URL, bearer token, timeout).
This module owns the *contract*: the request shape each rag-service route
expects, and the response shape agent-service consumes. Before it existed,
every call site in `flow_builder` hand-rolled a dict payload against a schema
that lives in another service, and two of those dicts had drifted out of
sync with rag-service:

* graph search sent ``collection_ids: [...]`` where rag-service's
  ``GraphSearchQuery`` requires ``collection_id: str`` (422, silently
  surfaced as "LLM provider error").
* document search returned chunks keyed ``page_content`` while every
  consumer read ``content``/``text`` — retrieved text was dropped and the
  model answered "not in the documents".

Funnelling every RAG call through here means a rag-service schema change is
caught in one place (and by the contract tests) instead of at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from config_manager import env
from error_contract import (
    ApplicationError,
    DependencyResponseError,
    raise_for_httpx_response,
)
from localization import get_locale
from pydantic import ValidationError

from core.http import outbound
from core.http.rag_http import (
    rag_auth_headers,
    rag_ingest_timeout_seconds,
    rag_timeout_seconds,
    rag_url,
)
from core.http.response_models import ResponseModel
from core.observability.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RagChunk:
    """One retrieved document chunk, normalised to a single text field.

    rag-service returns the chunk body under ``page_content``; the local
    vector-store fallback and older code paths use ``content``; some callers
    have historically produced ``text``. Consumers should never have to guess
    — they read :attr:`text`.
    """

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float | None = None
    id: str | None = None

    _TEXT_KEYS = ("page_content", "content", "text")

    @classmethod
    def from_wire(cls, raw: Any) -> RagChunk:
        if not isinstance(raw, dict):
            return cls(text=str(raw or ""))
        text = ""
        for key in cls._TEXT_KEYS:
            value = raw.get(key)
            if isinstance(value, str) and value:
                text = value
                break
        meta = raw.get("metadata")
        score = raw.get("score")
        identifier = raw.get("id")
        return cls(
            text=text,
            metadata=meta if isinstance(meta, dict) else {},
            score=float(score) if isinstance(score, (int, float)) else None,
            id=str(identifier) if identifier is not None else None,
        )

    def as_dict(self) -> dict[str, Any]:
        """The shape stored in flow ``scratch`` and read by DocumentContext.

        Always carries ``content`` so a downstream scan for document lists
        matches unambiguously.
        """
        return {"content": self.text, "metadata": self.metadata, "score": self.score}


@dataclass(frozen=True)
class RagCollection:
    """One RAG collection, normalised to a single id and a display label.

    rag-service's ``CollectionResponse`` keys the id under ``uuid`` and the
    human label under ``metadata.name``; older responses carried ``id`` and
    the raw ``name`` instead. Callers read :attr:`id` and :attr:`label` and
    never see which shape arrived.

    :attr:`name` is the raw collection (table) name. It stays exposed because
    callers key lookups by it as well as by id, and because hiding the default
    collection from a dropdown is their policy, not this module's.
    """

    id: str
    label: str
    name: str | None = None

    @classmethod
    def from_wire(cls, raw: Any) -> RagCollection | None:
        """Build a collection, or ``None`` for a row carrying no usable id."""
        if not isinstance(raw, dict):
            identifier = str(raw or "")
            return cls(id=identifier, label=identifier) if identifier else None

        identifier = raw.get("uuid") or raw.get("id")
        if not identifier:
            return None

        metadata = raw.get("metadata")
        meta_name = metadata.get("name") if isinstance(metadata, dict) else None
        name = raw.get("name")
        return cls(
            id=str(identifier),
            label=str(meta_name or name or identifier),
            name=str(name) if name else None,
        )


@dataclass(frozen=True)
class RagKnowledgeSource:
    """One entry of rag-service's knowledge selector, tagged with its kind."""

    id: str
    label: str
    kind: str


# ---------------------------------------------------------------------------
# Transport helpers
# ---------------------------------------------------------------------------


def parse_rag_response_model(payload: Any, http_status: int) -> Any:
    """Validate JSON envelopes, including array payloads and idle job nulls."""
    try:
        if not isinstance(payload, dict) or not {"statusCode", "message", "data", "error"} <= payload.keys():
            raise DependencyResponseError()
        result = ResponseModel[Any].model_validate(payload, strict=True)
    except ValidationError as exc:
        raise DependencyResponseError() from exc
    if result.statusCode != http_status:
        raise DependencyResponseError()
    if result.error is not None and 400 <= result.statusCode <= 599:
        raise ApplicationError(
            status_code=result.statusCode,
            code=result.error.code,
            message=result.error.message,
            message_key=None,
        )
    if not 200 <= result.statusCode < 300 or result.error is not None:
        raise DependencyResponseError()
    return result.data


async def _request(
    method: str,
    path: str,
    *,
    access_token: str | None,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
    dependency: str = outbound.RAG_SERVICE,
    timeout: float | None = None,
) -> Any:
    """One rag-service call. ``dependency``/``timeout`` default to the chat-retrieval
    policy; the ingest path names its own (minutes-long budget, separate breaker)."""
    url = rag_url(path)
    headers = {**rag_auth_headers(access_token), "X-Language": get_locale()}
    if extra_headers:
        headers = {**headers, **extra_headers}
    response = await outbound.request(
        dependency,
        method,
        url,
        timeout=timeout if timeout is not None else rag_timeout_seconds(),
        headers=headers,
        params=params,
        json=json_body,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise_for_httpx_response(response)
        raise DependencyResponseError() from exc
    return parse_rag_response_model(payload, response.status_code)


async def list_collection_records(*, access_token: str | None = None) -> list[dict[str, Any]]:
    """Return original collection records for a caller-scoped proxy."""
    data = await _request("GET", "/collections", access_token=access_token)
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise DependencyResponseError()
    return data


async def trigger_graph_build(collection_id: str, *, idempotency_key: str | None = None) -> dict[str, Any]:
    """Start an internal ingestion build with its required idempotency key.

    A caller that retries the same build passes the same ``idempotency_key`` so
    rag-service replays instead of starting a second build.
    """
    data = await _request(
        "POST",
        "/graph/build",
        access_token=None,
        json_body={"collection_id": collection_id},
        extra_headers={"Idempotency-Key": idempotency_key or str(uuid4())},
    )
    if not isinstance(data, dict):
        raise DependencyResponseError()
    return data


async def get_graph_build_progress(collection_id: str) -> dict[str, Any] | None:
    """Read a JSON build projection, preserving idle null progress."""
    data = await _request("GET", f"/graph/build/{collection_id}/status", access_token=None)
    if data is not None and not isinstance(data, dict):
        raise DependencyResponseError()
    return data


# ---------------------------------------------------------------------------
# Vector RAG
# ---------------------------------------------------------------------------


async def search_documents(
    collection_id: str,
    query: str,
    *,
    top_k: int = 4,
    threshold: float | None = None,
    access_token: str | None = None,
) -> list[RagChunk]:
    """Vector similarity search over a collection's document chunks.

    Returns normalised :class:`RagChunk` objects. An empty query or missing
    collection short-circuits to ``[]`` rather than calling rag-service.
    """
    if not query or not collection_id:
        return []
    raw = await _request(
        "POST",
        f"/collections/{collection_id}/documents/search",
        access_token=access_token,
        json_body={"query": query, "limit": top_k},
    )
    if not isinstance(raw, list):
        return []
    chunks = [RagChunk.from_wire(item) for item in raw]
    if threshold is not None:
        chunks = [c for c in chunks if (c.score if c.score is not None else 1.0) >= threshold]
    return chunks


# ---------------------------------------------------------------------------
# Graph RAG
# ---------------------------------------------------------------------------


async def search_graph(
    collection_id: str,
    query: str,
    *,
    limit: int = 10,
    access_token: str | None = None,
) -> Any:
    """Hybrid vector + graph-traversal search.

    rag-service's ``GraphSearchQuery`` takes a single ``collection_id``
    (string). Passing a list 422s.
    """
    return await _request(
        "POST",
        "/graph/search",
        access_token=access_token,
        json_body={"query": query, "collection_id": collection_id, "limit": limit},
    )


async def search_graph_entities(
    collection_id: str,
    query: str,
    *,
    entity_type: str | None = None,
    limit: int = 10,
    access_token: str | None = None,
) -> Any:
    params: dict[str, Any] = {"q": query, "limit": limit}
    if entity_type:
        params["entity_type"] = entity_type
    return await _request(
        "GET",
        f"/graph/collections/{collection_id}/search/entities",
        access_token=access_token,
        params=params,
    )


async def graph_neighborhood(
    collection_id: str,
    entity_id: str,
    *,
    depth: int = 1,
    limit: int = 20,
    access_token: str | None = None,
) -> Any:
    return await _request(
        "GET",
        f"/graph/collections/{collection_id}/neighborhood",
        access_token=access_token,
        params={"node_id": entity_id, "depth": depth, "limit": limit},
    )


async def graph_stats(
    collection_id: str,
    *,
    access_token: str | None = None,
) -> Any:
    return await _request(
        "GET",
        f"/graph/collections/{collection_id}/stats",
        access_token=access_token,
    )


# ---------------------------------------------------------------------------
# Datasource ingestion (connector-managed collections)
#
# agent-service's connector runtime is the sole writer of these collections.
# rag-service owns the Milvus connection and the embedding model on this
# path too — agent-service only ever turns a synced record into text, never
# opens a vector-store connection itself. See docs/adr or the migration that
# introduced this module for why: the two services used to address the same
# physical Milvus collection independently (duplicated connection/naming
# code, and a real risk of the two picking different embedding models for
# the same collection).
# ---------------------------------------------------------------------------


async def ingest_datasource_records(
    collection_id: str,
    documents: list[dict[str, Any]],
    *,
    clear_existing: bool = False,
    idempotency_key: str | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Send one batch of connector-synced records for chunking + embedding.

    ``documents`` is ``[{"content": str, "metadata": dict, "record_key": str}, ...]``
    — one per synced record, not yet chunked; rag-service splits, embeds and
    writes them. A document with a ``record_key`` replaces the chunks an earlier
    write stored under that key. Returns ``{"chunks_indexed", "chunk_char_total",
    "chunk_token_total", "chunks_replaced"}``.
    """
    extra_headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
    return await _request(
        "POST",
        f"/datasources/{collection_id}/records",
        access_token=access_token,
        json_body={"documents": documents, "clear_existing": clear_existing},
        extra_headers=extra_headers,
        # The batch is split and embedded inside this request: minutes, on a pool and
        # breaker of its own so a slow ingest never opens the chat-retrieval circuit.
        dependency=outbound.RAG_SERVICE_INGEST,
        timeout=rag_ingest_timeout_seconds(),
    )


async def retire_datasource_runs(
    collection_id: str,
    *,
    keep_job_id: str,
    idempotency_key: str | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Keep the chunks of one sync run and remove every other chunk of the collection.

    The end of an ``overwrite`` sync: its records landed next to the previous
    version (``_sync_job_id`` in every chunk's metadata), which stayed searchable
    meanwhile; now it takes the previous version's place. Returns
    ``{"chunks_removed"}``.
    """
    extra_headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
    return await _request(
        "POST",
        f"/datasources/{collection_id}/records/retire",
        access_token=access_token,
        json_body={"keep_job_id": keep_job_id},
        extra_headers=extra_headers,
        dependency=outbound.RAG_SERVICE_INGEST,  # a Milvus scan and delete: the ingest budget
        timeout=rag_ingest_timeout_seconds(),
    )


async def delete_datasource_records(
    collection_id: str,
    *,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Remove everything rag-service stores for a datasource (its Milvus table).

    Called while a datasource is deleted, before its collection row goes: the
    row names the table, and without it the chunks could not be reached any
    more. Returns ``{"chunks_removed"}``; a 404 means rag-service holds nothing
    for the collection.
    """
    return await _request(
        "DELETE",
        f"/datasources/{collection_id}/records",
        access_token=access_token,
        dependency=outbound.RAG_SERVICE_INGEST,  # a Milvus drop: the ingest budget
        timeout=rag_ingest_timeout_seconds(),
    )


async def fetch_datasource_entities(
    collection_id: str,
    *,
    limit: int = 10,
    offset: int = 0,
    include_stats: bool = False,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Raw (unaggregated) Milvus entities for a connector-managed collection.

    Returns ``{"count": int, "entities": [{"content", "metadata"}, ...], "stats": dict | None}``.
    """
    return await _request(
        "GET",
        f"/datasources/{collection_id}/entities",
        access_token=access_token,
        params={"limit": limit, "offset": offset, "include_stats": include_stats},
    )


# ---------------------------------------------------------------------------
# Long-term memory (semantic search over user facts)
#
# Unlike every other route in this module, memory endpoints
# (src.memory.router) authenticate via direct x-internal-token +
# x-user-id delegation, not the Authorization: Bearer scheme _request()
# builds: there is no per-user access_token to forward here (recall never
# runs on a request that's carrying the end user's own token), and the
# memory router's trusted-context resolution reads x-user-id directly
# rather than decoding a JWT or checking an API key.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemoryFactHit:
    """One semantically-matched user fact."""

    fact_id: str
    content: str
    score: float


def _memory_headers(user_id: str) -> dict[str, str]:
    """Authenticate as the service and delegate the end user's identity.

    rag-service resolves an internal caller from ``x-internal-token``
    (see ``src.shared.gateway_identity``), not from the bearer header
    the shared transport sets, and it refuses a memory call that names no
    delegated user.
    """
    token = (env.INTERNAL_SERVICE_TOKEN or "").strip()
    return {"x-internal-token": token, "x-user-id": user_id}


async def search_memory_facts(user_id: str, query: str, *, limit: int = 5) -> list[MemoryFactHit]:
    """Semantic search over one user's long-term-memory facts.

    Fails open to `[]` on any error (bad response, timeout, connection
    failure): a chat turn must degrade to "no recalled memories," never
    break, when rag-service or Milvus is unavailable.
    """
    if not user_id or not query.strip():
        return []
    try:
        raw = await _request(
            "POST",
            "/memory/search",
            access_token=None,
            json_body={"query": query, "limit": limit},
            extra_headers=_memory_headers(user_id),
        )
    except Exception as exc:
        logger.warning("Memory search failed for user %r: %s", user_id, exc)
        return []

    hits = raw.get("hits") if isinstance(raw, dict) else None
    if not isinstance(hits, list):
        return []
    return [
        MemoryFactHit(
            fact_id=str(item.get("fact_id", "")),
            content=str(item.get("content", "")),
            score=float(item.get("score", 0.0)),
        )
        for item in hits
        if isinstance(item, dict)
    ]


# Collection catalog
# ---------------------------------------------------------------------------


def _collection_rows(raw: Any) -> list[Any]:
    """Unwrap the row list from a catalog response, dict-wrapped or bare."""
    if isinstance(raw, dict):
        for key in ("collections", "collection_ids"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
        return []
    return raw if isinstance(raw, list) else []


async def list_collections(*, access_token: str | None = None) -> list[RagCollection]:
    """Every RAG collection rag-service knows about.

    Raises on transport or status failure so a caller can fall back to its own
    source; an empty catalog comes back as an empty list.
    """
    raw = await _request("GET", "/collections", access_token=access_token)
    return [c for row in _collection_rows(raw) if (c := RagCollection.from_wire(row))]


async def list_graph_collections(*, access_token: str | None = None) -> list[RagCollection]:
    """Collections that have a knowledge graph built.

    This endpoint has returned three shapes: objects under ``collections``,
    bare ids under ``collection_ids``, and a plain list of ids. All three
    arrive here as collections; one carrying only an id gets its id as the
    label, which the caller is expected to replace from its own name map.
    """
    raw = await _request("GET", "/graph/collections", access_token=access_token)
    return [c for row in _collection_rows(raw) if (c := RagCollection.from_wire(row))]


async def list_knowledge_sources(*, access_token: str | None = None) -> list[RagKnowledgeSource]:
    """Datasources offered by the knowledge selector, tagged by kind."""
    raw = await _request("GET", "/datasources/knowledge-selector", access_token=access_token)
    if not isinstance(raw, dict):
        return []

    sources: list[RagKnowledgeSource] = []
    for kind in ("document_processing", "knowledge_graph"):
        for row in raw.get(kind) or []:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            identifier = str(row["id"])
            sources.append(RagKnowledgeSource(id=identifier, label=str(row.get("name") or identifier), kind=kind))
    return sources
