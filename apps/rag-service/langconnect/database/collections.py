"""Collection and Document managers.

These classes provide the **business-logic** layer that the API routes
consume.  All database access is delegated to the repository classes
under ``langconnect.database.postgres.repositories``.

The ``CollectionsManager`` handles collection CRUD.
The ``Collection`` handles document-level operations within a collection.
"""

from __future__ import annotations

import builtins
import logging
from typing import Any, Optional

from fastapi import status
from fastapi.exceptions import HTTPException
from langchain_core.documents import Document

from langconnect.database.connection import get_vectorstore
from langconnect.database.postgres.repositories.collection_repo import (
    CollectionRepository,
)
from langconnect.database.postgres.repositories.document_repo import (
    DocumentRepository,
)
from langconnect.models.collection import CollectionDetails

logger = logging.getLogger(__name__)


class CollectionsManager:
    """Use to create, delete, update, and list document collections."""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self._repo = CollectionRepository(user_id)

    @staticmethod
    async def setup() -> None:
        """Run any necessary initialisation (vectorstore bootstrap)."""
        logger.info("Starting vector store initialization...")
        from langconnect import config
        if config.VECTOR_DB_PROVIDER.lower() != "pgvector":
            logger.info("Vector DB provider: %s — skipping PGVector table bootstrap.", config.VECTOR_DB_PROVIDER)
        else:
            get_vectorstore()
        logger.info("Vector store initialization complete.")

    async def list(self) -> list[CollectionDetails]:
        """List all collections owned by the given user."""
        return await self._repo.list_collections()

    async def get(self, collection_id: str) -> CollectionDetails | None:
        """Fetch a single collection by UUID, ensuring the user owns it."""
        return await self._repo.get_collection(collection_id)

    async def create(
        self,
        collection_name: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> CollectionDetails | None:
        """Create a new collection."""
        return await self._repo.create_collection(collection_name, metadata)

    async def update(
        self,
        collection_id: str,
        *,
        name: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> CollectionDetails:
        """Update collection metadata / name."""
        if metadata is None and name is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must update at least 1 attribute.",
            )

        result = await self._repo.update_collection(
            collection_id, name=name, metadata=metadata
        )
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Collection '{collection_id}' not found or not owned by you.",
            )
        return result

    async def delete(self, collection_id: str) -> int:
        """Delete a collection by UUID.  Returns rows deleted."""
        return await self._repo.delete_collection(collection_id)


class Collection:
    """A collection of documents.

    Use to add, delete, list, and search documents within a collection.
    """

    def __init__(self, collection_id: str, user_id: str) -> None:
        self.collection_id = collection_id
        self.user_id = user_id
        self._doc_repo = DocumentRepository(collection_id, user_id)
        self._col_repo = CollectionRepository(user_id)

    async def _get_details_or_raise(self) -> dict[str, Any]:
        """Get collection details if it exists, otherwise raise 404."""
        details = await self._col_repo.get_collection(self.collection_id)
        if not details:
            raise HTTPException(status_code=404, detail="Collection not found")
        return details

    async def upsert(self, documents: list[Document]) -> list[str]:
        """Add one or more documents to the collection."""
        from langconnect import config

        details = await self._get_details_or_raise()
        store = get_vectorstore(collection_name=details["table_id"])
        ids = store.add_documents(documents)

        # Milvus does not populate langchain_pg_embedding; persist chunk metadata
        # to Postgres so list/get/chunk APIs and graph build remain functional.
        if config.VECTOR_DB_PROVIDER.lower() != "pgvector":
            await self._doc_repo.upsert_documents(
                ids=[str(i) for i in ids],
                documents=[doc.page_content for doc in documents],
                metadatas=[doc.metadata or {} for doc in documents],
            )

        return ids

    async def delete(self, *, file_id: Optional[str] = None) -> bool:
        """Delete embeddings by file id."""
        deleted_count = await self._doc_repo.delete_by_file_id(file_id)
        logger.info("Deleted %d embeddings for file %r.", deleted_count, file_id)
        if deleted_count == 0:
            await self._get_details_or_raise()
        return True

    async def list(self, *, limit: int = 10, offset: int = 0) -> list[dict[str, Any]]:
        """List one representative chunk per file in this collection."""
        docs = await self._doc_repo.list_documents(limit=limit, offset=offset)
        if not docs:
            await self._get_details_or_raise()
        return docs

    async def get(self, document_id: str) -> dict[str, Any]:
        """Fetch a single chunk by its UUID, verifying collection ownership."""
        result = await self._doc_repo.get_document(document_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return result

    async def get_chunks(self, file_id: str) -> list[dict[str, Any]]:
        """Fetch all chunks associated with a file_id, verifying collection ownership."""
        return await self._doc_repo.list_chunks_by_file_id(file_id)

    async def search(
        self, query: str, *, limit: int = 4
    ) -> builtins.list[dict[str, Any]]:
        """Run a semantic similarity search in the vector store."""
        details = await self._get_details_or_raise()
        store = get_vectorstore(collection_name=details["table_id"])
        results = store.similarity_search_with_score(query, k=limit)
        return [
            {
                "id": doc.id or (doc.metadata.get("file_id") if doc.metadata else None),
                "page_content": doc.page_content,
                "metadata": doc.metadata or {},
                "score": score,
            }
            for doc, score in results
        ]
