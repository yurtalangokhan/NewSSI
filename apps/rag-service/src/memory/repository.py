"""Milvus adapter for the user memory-facts index.

The only module that opens a Milvus connection or embeds text for user
facts. Backed by one fixed, shared collection (not one per user or one per
RAG collection like documents/graph): facts have no user-created
"collection" concept, so isolation is a user_id metadata filter -- the
same pattern collections/documents already use for file_id.

Writes (upsert/delete) raise shared MemoryUpsertError/MemoryDeleteError on failure,
matching documents.service.Collection.delete's convention of reporting a
failed Milvus call honestly rather than silently reporting success. Search
is the one operation that fails open (returns no hits) instead of raising:
it runs on the per-chat-turn recall path, where a Milvus hiccup must
degrade a turn to "no recalled memories," never break it.
"""

from __future__ import annotations

import asyncio
from typing import Any

from config_manager import env
from error_contract import ApplicationError, MemoryDeleteError, MemoryUpsertError
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore

from src.memory.contract import MemoryFactHit
from src.shared.milvus_expr import metadata_equals
from src.shared.observability import get_logger
from src.shared.vectorstore import get_vectorstore

logger = get_logger(__name__)

MEMORY_COLLECTION_NAME = "user_memory_facts"

# Matches the metadata_field="metadata" every Milvus store in this codebase
# is constructed with (src.shared.vectorstore._build_milvus_store),
# so this is read as a plain constant rather than the store's own private
# `_metadata_field` attribute.
_METADATA_FIELD = "metadata"

# COSINE rather than the library's default L2 distance: scores land in a
# fixed, intuitive [-1, 1] similarity range, which is what a "keep if
# score >= threshold" relevance filter assumes -- an unbounded raw
# distance is much harder to tune a meaningful floor for.
_INDEX_PARAMS: dict[str, Any] = {
    "metric_type": "COSINE",
    "index_type": "AUTOINDEX",
    "params": {},
}
_SEARCH_PARAMS: dict[str, Any] = {"metric_type": "COSINE", "params": {}}


def _get_store() -> VectorStore:
    return get_vectorstore(
        collection_name=MEMORY_COLLECTION_NAME,
        embeddings=env.DEFAULT_EMBEDDINGS,
        index_params=_INDEX_PARAMS,
        search_params=_SEARCH_PARAMS,
    )


def _user_expr(user_id: str) -> str:
    return metadata_equals(_METADATA_FIELD, "user_id", user_id)


async def upsert_fact(*, user_id: str, fact_id: str, content: str) -> None:
    """Embed and store one fact, keyed by (user_id, fact_id) in metadata."""
    document = Document(
        page_content=content,
        metadata={"user_id": user_id, "fact_id": fact_id},
    )
    try:
        store = _get_store()
        # add_documents embeds and writes synchronously; offloaded so it
        # doesn't stall the event loop (same reasoning as documents.service).
        await asyncio.to_thread(store.add_documents, [document])
    except ApplicationError:
        raise
    except Exception as exc:
        logger.warning("Milvus upsert failed for user %r fact %r: %s", user_id, fact_id, exc)
        raise MemoryUpsertError(
            details={"user_id": user_id, "fact_id": fact_id},
        ) from exc


async def delete_fact(*, user_id: str, fact_id: str) -> None:
    """Remove one fact's embedding."""
    expr = f"{_user_expr(user_id)} && {metadata_equals(_METADATA_FIELD, 'fact_id', fact_id)}"
    try:
        store = _get_store()
        await asyncio.to_thread(store.delete, expr=expr)
    except ApplicationError:
        raise
    except Exception as exc:
        logger.warning("Milvus delete failed for user %r fact %r: %s", user_id, fact_id, exc)
        raise MemoryDeleteError(
            details={"user_id": user_id, "fact_id": fact_id},
        ) from exc


async def delete_all_facts(*, user_id: str) -> None:
    """Remove every fact embedding stored for the user."""
    try:
        store = _get_store()
        await asyncio.to_thread(store.delete, expr=_user_expr(user_id))
    except ApplicationError:
        raise
    except Exception as exc:
        logger.warning("Milvus delete-all failed for user %r: %s", user_id, exc)
        raise MemoryDeleteError(
            details={"user_id": user_id},
        ) from exc


async def search_facts(*, user_id: str, query: str, limit: int) -> tuple[MemoryFactHit, ...]:
    """Semantic search within one user's facts. Fails open to an empty tuple."""
    try:
        store = _get_store()
        results = await asyncio.to_thread(
            store.similarity_search_with_score,
            query,
            k=limit,
            expr=_user_expr(user_id),
        )
    except Exception as exc:
        logger.warning("Milvus search failed for user %r: %s", user_id, exc)
        return ()

    hits: list[MemoryFactHit] = []
    for document, score in results:
        fact_id = (document.metadata or {}).get("fact_id")
        if not fact_id:
            # A row without our own fact_id metadata isn't one of ours to
            # surface -- skip it rather than returning a hit callers can't
            # act on (e.g. to later delete).
            continue
        logger.info(
            "Memory search hit: user=%r fact_id=%r score=%.4f content=%r",
            user_id,
            fact_id,
            float(score),
            document.page_content[:80],
        )
        hits.append(MemoryFactHit(fact_id=str(fact_id), content=document.page_content, score=float(score)))
    return tuple(hits)
