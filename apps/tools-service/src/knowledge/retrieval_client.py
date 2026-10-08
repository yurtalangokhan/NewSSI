"""Async client for rag-service's agent-facing ``POST /retrieval`` contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

RetrievalMode = Literal["vector", "graph"]

_DEFAULT_TIMEOUT_SECONDS = 30.0


class RagRetrievalError(Exception):
    """rag-service could not answer. The message never carries URLs or headers."""


@dataclass(frozen=True)
class RetrievalIdentity:
    """The delegated caller rag-service authorizes the collection against."""

    user_id: str | None = None
    tenant_id: str | None = None


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class RagHit(_WireModel):
    id: str | None = None
    content: str = ""
    score: float | None = None
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagGraphNode(_WireModel):
    id: str
    name: str
    label: str = "Entity"
    matched: bool = False
    score: float | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class RagGraphEdge(_WireModel):
    id: str | None = None
    source: str
    target: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class RagGraph(_WireModel):
    nodes: tuple[RagGraphNode, ...] = ()
    edges: tuple[RagGraphEdge, ...] = ()


class RagRetrievalResponse(_WireModel):
    """One collection's retrieval answer."""

    collection_id: str
    collection_name: str | None = None
    hits: tuple[RagHit, ...] = ()
    context: str = ""
    graph: RagGraph | None = None


class RagRetrievalClient:
    """Calls ``/retrieval`` with the internal token and delegated identity."""

    def __init__(
        self,
        *,
        retrieval_url: str,
        internal_token: str,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._retrieval_url = retrieval_url
        self._internal_token = internal_token
        self._timeout = timeout
        self._transport = transport

    async def retrieve(
        self,
        *,
        query: str,
        collection_id: str,
        mode: RetrievalMode,
        limit: int,
        identity: RetrievalIdentity,
    ) -> RagRetrievalResponse:
        payload = {"query": query, "collection_id": collection_id, "kind": mode, "limit": limit}
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.post(self._retrieval_url, json=payload, headers=self._headers(identity))
                response.raise_for_status()
                envelope = response.json()
                if not isinstance(envelope, dict) or envelope.get("statusCode") != response.status_code:
                    raise ValueError("Invalid retrieval response envelope")
                data = envelope.get("data")
                if envelope.get("error") is not None or not isinstance(data, dict):
                    raise RagRetrievalError("ApplicationError")
                return RagRetrievalResponse.model_validate(data)
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            # httpx errors embed the internal URL; keep only the type.
            raise RagRetrievalError(type(exc).__name__) from exc

    def _headers(self, identity: RetrievalIdentity) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._internal_token:
            headers["x-internal-token"] = self._internal_token
        if identity.user_id:
            headers["x-user-id"] = identity.user_id
        if identity.tenant_id:
            headers["x-tenant-id"] = identity.tenant_id
        return headers
