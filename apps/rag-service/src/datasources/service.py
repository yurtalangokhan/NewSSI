"""Knowledge-source selection and connector record operations."""

import asyncio
from typing import Any

from error_contract import DatabaseConnectionError, DatabaseOperationError
from langchain_core.documents import Document

from src.collections.naming import (
    collection_connector_type,
    collection_display_name,
    collection_sync_status,
)
from src.collections.service import CollectionsManager
from src.datasources.schemas import DatasourceRecordIn
from src.documents.processor import TEXT_SPLITTER
from src.documents.service import RECORD_KEY_METADATA_KEY, Collection
from src.graph import GraphStore
from src.shared.observability import get_logger

logger = get_logger(__name__)


async def knowledge_selector(user_id: str) -> dict[str, list[dict[str, Any]]]:
    """Return categorised knowledge sources for the agent editor.

    Returns two lists:
    - ``document_processing``: all Milvus-backed collections (vector similarity search)
    - ``knowledge_graph``: collections that have a built knowledge graph in Neo4j
    """
    # 1. Fetch collections visible to the current user. Do not use the
    # internal identity here; the agent editor must not expose other users'
    # private collections or stale test/dev rows.
    all_collections = await CollectionsManager(user_id).list()

    def _build_item(col: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": col["uuid"],
            "name": collection_display_name(col),
            "connector_type": collection_connector_type(col),
            "sync_status": collection_sync_status(col),
        }

    document_processing = [_build_item(col) for col in all_collections]
    # Keep connector-backed datasources first so they are easier to find in agent setup.
    document_processing.sort(
        key=lambda item: (
            item.get("connector_type", "") == "",
            item.get("name", "").lower(),
        )
    )

    # 2. Fetch collection IDs that have a built knowledge graph
    knowledge_graph: list[dict[str, Any]] = []
    try:
        graph_collection_ids: list[str] = await GraphStore.list_graph_collection_ids()

        # Build a lookup for collection details
        col_lookup = {col["uuid"]: col for col in all_collections}

        for cid in graph_collection_ids:
            col = col_lookup.get(cid)
            if col:
                knowledge_graph.append(_build_item(col))
    except (DatabaseConnectionError, DatabaseOperationError):
        logger.warning("Neo4j is not available — knowledge_graph list will be empty.")

    return {
        "document_processing": document_processing,
        "knowledge_graph": knowledge_graph,
    }


# ---------------------------------------------------------------------------
# Connector-managed record ingestion / raw reads
#
# agent-service owns the connector pipeline (its in-process connector
# runtime): it turns each synced record into a LangChain Document
# (connector-specific field mapping) and streams batches here during a sync.
# This module owns everything past that point -- chunking, embedding, and the
# Milvus read/write -- so agent-service never has to open a Milvus connection
# or pick an embedding model itself.
# ---------------------------------------------------------------------------


def _latest_per_record_key(
    documents: list[DatasourceRecordIn],
) -> list[DatasourceRecordIn]:
    """Drop every document that a later one with the same record key supersedes."""
    last_index = {document.record_key: index for index, document in enumerate(documents) if document.record_key}
    return [
        document
        for index, document in enumerate(documents)
        if not document.record_key or last_index[document.record_key] == index
    ]


def _to_document(record: DatasourceRecordIn) -> Document:
    """Build the document to split, its record key in the metadata of every chunk."""
    metadata = dict(record.metadata)
    if record.record_key:
        metadata[RECORD_KEY_METADATA_KEY] = record.record_key
    return Document(page_content=record.content, metadata=metadata)


async def ingest_datasource_records(
    user_id: str,
    collection_id: str,
    documents: list[DatasourceRecordIn],
    *,
    clear_existing: bool = False,
) -> dict[str, Any]:
    """Chunk, embed and store one batch of connector-synced records.

    Called by agent-service's connector runtime as records stream in
    during a sync -- the only writer of connector-managed collections. Never
    used for user file uploads (see ``documents_create`` in ``documents.py``
    for that path, which explicitly refuses connector-managed collections).

    A document with a ``record_key`` replaces the chunks stored for that key
    by an earlier write, so sending a batch again leaves one version of each
    record. A document without one is appended.
    """
    collection = Collection(collection_id=str(collection_id), user_id=user_id)

    if clear_existing:
        await collection.clear()

    records = _latest_per_record_key(documents)
    record_keys = [record.record_key for record in records if record.record_key]
    chunks = await asyncio.to_thread(TEXT_SPLITTER.split_documents, [_to_document(record) for record in records])

    chunks_replaced = 0
    if record_keys:
        # Also when the new versions gave no chunk at all: what was stored for
        # these records is out of date either way.
        chunks_replaced = await collection.replace_records(record_keys, chunks)
    elif chunks:
        await collection.upsert(chunks)

    chunk_char_total = sum(len(c.page_content) for c in chunks)
    chunk_token_total = sum(max(len(c.page_content.split()), len(c.page_content) // 4) for c in chunks)

    return {
        "chunks_indexed": len(chunks),
        "chunk_char_total": chunk_char_total,
        "chunk_token_total": chunk_token_total,
        "chunks_replaced": chunks_replaced,
    }


async def retire_datasource_runs(user_id: str, collection_id: str, keep_job_id: str) -> dict[str, Any]:
    """Keep the chunks of one sync run and remove every other chunk of the collection.

    The end of an ``overwrite`` sync in agent-service's connector runtime: the
    run wrote its records next to the previous version, which stayed searchable
    the whole time, and now replaces it. Chunks written before runs were tagged
    (no ``_sync_job_id``) go as well.
    """
    collection = Collection(collection_id=str(collection_id), user_id=user_id)
    return {"chunks_removed": await collection.retire_other_runs(keep_job_id)}


async def delete_datasource_records(user_id: str, collection_id: str) -> dict[str, Any]:
    """Remove everything stored for a datasource: its Milvus table goes.

    agent-service calls this while it deletes the datasource, before the
    collection row that names the table is deleted; afterwards the chunks
    could not be reached any more. A repeated call finds no table and removes
    nothing.
    """
    collection = Collection(collection_id=str(collection_id), user_id=user_id)
    return {"chunks_removed": await collection.drop()}


async def list_datasource_entities(
    user_id: str,
    collection_id: str,
    limit: int = 10,
    offset: int = 0,
    *,
    include_stats: bool = False,
) -> dict[str, Any]:
    """Raw (unaggregated) Milvus entity count / page / stats for a datasource.

    Distinct from ``documents_list`` (which groups chunks by file_id) --
    connector-managed collections have no file_id per row, so every row is
    its own entity here.
    """
    collection = Collection(collection_id=str(collection_id), user_id=user_id)
    count = await collection.entity_count()
    entities = await collection.list_raw_entities(limit=limit, offset=offset)
    stats = await collection.entity_stats() if include_stats else None
    return {"count": count, "entities": entities, "stats": stats}
