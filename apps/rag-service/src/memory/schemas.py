"""HTTP request/response bodies for the memory-facts domain."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.memory.contract import DEFAULT_SEARCH_LIMIT, MAX_SEARCH_LIMIT


class UpsertFactRequest(BaseModel):
    """Body for indexing (or re-indexing) one fact."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str
    content: str


class SearchFactsRequest(BaseModel):
    """Body for a semantic search over the trusted user's facts."""

    model_config = ConfigDict(extra="forbid")

    query: str
    limit: int = Field(default=DEFAULT_SEARCH_LIMIT, ge=1, le=MAX_SEARCH_LIMIT)


class MemoryFactHitBody(BaseModel):
    """One semantically-matched fact in the HTTP response."""

    fact_id: str
    content: str
    score: float
    vector_score: float | None = None
    bm25_score: float | None = None


class SearchFactsResponse(BaseModel):
    """HTTP response for a semantic search."""

    hits: list[MemoryFactHitBody]
