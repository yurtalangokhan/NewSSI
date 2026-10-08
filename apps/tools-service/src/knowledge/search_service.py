"""Runs one knowledge search across collections and records its evidence."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import time

from .evidence import EvidenceCollection, KnowledgeEvidence
from .retrieval_client import RagRetrievalClient, RagRetrievalResponse, RetrievalIdentity
from .search_strategies import SearchStrategy

#: Upper bound on rag-service calls in flight for one search.
MAX_CONCURRENT_COLLECTION_SEARCHES = 5


@dataclass(frozen=True)
class KnowledgeSearchOutcome:
    """The text the model reads and the evidence the UI renders, from one call."""

    model_text: str
    evidence: KnowledgeEvidence


class KnowledgeSearchService:
    """Query the collections concurrently (bounded), then let the strategy shape the answer."""

    def __init__(
        self,
        client: RagRetrievalClient,
        *,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._client = client
        self._clock = clock

    async def search(
        self,
        *,
        strategy: SearchStrategy,
        tool: str,
        query: str,
        collection_ids: Sequence[str],
        limit: int,
        identity: RetrievalIdentity,
    ) -> KnowledgeSearchOutcome:
        """Raises ``RagRetrievalError`` for the first collection, in order, that cannot be searched."""
        started = self._clock()
        permits = asyncio.Semaphore(MAX_CONCURRENT_COLLECTION_SEARCHES)

        async def retrieve(collection_id: str) -> RagRetrievalResponse:
            async with permits:
                return await self._client.retrieve(
                    query=query,
                    collection_id=collection_id,
                    mode=strategy.mode,
                    limit=limit,
                    identity=identity,
                )

        results = await asyncio.gather(
            *(retrieve(collection_id) for collection_id in collection_ids),
            return_exceptions=True,
        )
        responses: list[RagRetrievalResponse] = []
        for result in results:
            if isinstance(result, BaseException):
                raise result
            responses.append(result)
        assembled = strategy.assemble(responses)
        evidence = KnowledgeEvidence(
            kind=strategy.evidence_kind,
            tool=tool,
            query=query,
            collections=tuple(
                EvidenceCollection(id=response.collection_id, name=response.collection_name) for response in responses
            ),
            chunks=assembled.chunks,
            graph=assembled.graph,
            model_context=assembled.model_text,
            elapsed_ms=round((self._clock() - started) * 1000),
        )
        return KnowledgeSearchOutcome(model_text=assembled.model_text, evidence=evidence)
