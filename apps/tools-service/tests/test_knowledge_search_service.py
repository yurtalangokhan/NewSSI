from __future__ import annotations

import asyncio

import pytest

from src.knowledge.retrieval_client import (
    RagHit,
    RagRetrievalError,
    RagRetrievalResponse,
    RetrievalIdentity,
)
from src.knowledge.search_service import MAX_CONCURRENT_COLLECTION_SEARCHES, KnowledgeSearchService
from src.knowledge.search_strategies import DocumentSearchStrategy


class _ConcurrentClient:
    """Answers each collection only after every collection has been asked."""

    def __init__(self, *, failing: frozenset[str] = frozenset()) -> None:
        self._failing = failing
        self._expected = 0
        self._asked: list[str] = []
        self._all_asked = asyncio.Event()

    def expect(self, count: int) -> None:
        self._expected = count

    async def retrieve(self, *, collection_id: str, **_: object) -> RagRetrievalResponse:
        self._asked.append(collection_id)
        if len(self._asked) == self._expected:
            self._all_asked.set()
        await asyncio.wait_for(self._all_asked.wait(), timeout=1)
        if collection_id in self._failing:
            raise RagRetrievalError(f"failed:{collection_id}")
        return RagRetrievalResponse(
            collection_id=collection_id,
            hits=(RagHit(id=f"hit-{collection_id}", content=f"text {collection_id}"),),
        )


async def _search(client: _ConcurrentClient, collection_ids: list[str]):
    client.expect(len(collection_ids))
    return await KnowledgeSearchService(client).search(
        strategy=DocumentSearchStrategy(),
        tool="database_search",
        query="q",
        collection_ids=collection_ids,
        limit=5,
        identity=RetrievalIdentity(),
    )


async def test_collections_are_searched_concurrently_and_keep_their_order() -> None:
    outcome = await _search(_ConcurrentClient(), ["a", "b", "c"])

    assert [c.id for c in outcome.evidence.collections] == ["a", "b", "c"]
    assert [chunk.collection_id for chunk in outcome.evidence.chunks] == ["a", "b", "c"]
    assert [chunk.ref for chunk in outcome.evidence.chunks] == [1, 2, 3]


async def test_a_failing_collection_fails_the_search_with_the_first_failure_in_order() -> None:
    client = _ConcurrentClient(failing=frozenset({"b", "c"}))

    with pytest.raises(RagRetrievalError, match="failed:b"):
        await _search(client, ["a", "b", "c"])


class _PeakClient:
    def __init__(self) -> None:
        self.in_flight = 0
        self.peak = 0

    async def retrieve(self, *, collection_id: str, **_: object) -> RagRetrievalResponse:
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1
        return RagRetrievalResponse(collection_id=collection_id, hits=())


async def test_concurrent_collection_searches_are_bounded() -> None:
    client = _PeakClient()
    collection_ids = [f"c{i}" for i in range(MAX_CONCURRENT_COLLECTION_SEARCHES * 3)]

    outcome = await KnowledgeSearchService(client).search(
        strategy=DocumentSearchStrategy(),
        tool="database_search",
        query="q",
        collection_ids=collection_ids,
        limit=5,
        identity=RetrievalIdentity(),
    )

    assert client.peak == MAX_CONCURRENT_COLLECTION_SEARCHES
    assert [c.id for c in outcome.evidence.collections] == collection_ids
