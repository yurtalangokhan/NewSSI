# Copyright (c) 2026 Agentic AI Platform
"""Collection metadata lifecycle.

``CollectionsManager`` owns collection *metadata* (name, owner, connector
type, etc.), which lives in Postgres (``langchain_pg_collection``) — list,
get, create, update, delete, all permission-gated through
``src.shared.authorization``. It never touches Milvus itself; the chunk /
embedding data behind each collection is ``documents.service.Collection``'s
job.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from config_manager import env
from error_contract import (
    BadRequestError,
    CollectionNotFoundError,
    DatabaseOperationError,
)

from src.collections.repository import (
    CollectionRepository,
)
from src.shared.authorization import get_authorization_client
from src.shared.observability import get_logger

if TYPE_CHECKING:
    from src.collections.schemas import CollectionDetails

logger = get_logger(__name__)


class CollectionsManager:
    """Use to create, delete, update, and list document collections."""

    def __init__(self, user_id: str) -> None:
        """Bind collection metadata access to the requesting user."""
        self.user_id = user_id
        self._repo = CollectionRepository(user_id)

    @staticmethod
    async def setup() -> None:
        """Run any necessary initialisation (vectorstore bootstrap)."""
        logger.info("Starting vector store initialization...")
        from src.shared.vectorstore import (
            get_vectorstore,
        )

        if env.VECTOR_DB_PROVIDER.lower() != "pgvector":
            logger.info(
                "Vector DB provider: %s — skipping PGVector table bootstrap.",
                env.VECTOR_DB_PROVIDER,
            )
        else:
            get_vectorstore()
        logger.info("Vector store initialization complete.")

    async def list(self) -> list[CollectionDetails]:
        """List owned, ingestion-visible, and permission-granted collections."""
        if self.user_id == "internal-service":
            return await self._repo.list_collections()
        accessible_ids = await get_authorization_client().get_user_accessible_collections(self.user_id)
        return await self._repo.list_collections(accessible_ids=accessible_ids)

    async def get(self, collection_id: str, required_permission: str = "read") -> CollectionDetails | None:
        """Resolve collection access without changing the requesting identity."""
        # This lookup is visibility-filtered (own, internal-service, or ownerless
        # ingestion rows), so the ``read`` fast path below never exposes another
        # user's private collection; those fall through to the grant check.
        details = await self._repo.get_collection(collection_id)
        if details and (
            required_permission == "read"
            or self.user_id == "internal-service"
            or details.get("metadata", {}).get("owner_id") == self.user_id
        ):
            return details
        access = await get_authorization_client().check_collection_access(
            self.user_id, collection_id, required_permission
        )
        if access.get("allowed") is not True:
            return None
        return details or await self._repo.get_collection(collection_id, accessible_ids=[collection_id])

    async def create(
        self,
        collection_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> CollectionDetails | None:
        """Create a new collection."""
        return await self._repo.create_collection(collection_name, metadata)

    async def update(
        self,
        collection_id: str,
        *,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CollectionDetails:
        """Update collection metadata / name."""
        if metadata is None and name is None:
            raise BadRequestError(
                code="collection.update_requires_attribute",
                message_key="errors.rag.collection.update_requires_attribute",
            )

        if await self.get(collection_id, "write") is None:
            self._raise_not_found(collection_id)
        result = await self._repo.update_collection(
            collection_id,
            name=name,
            metadata=metadata,
            accessible_ids=[collection_id],
        )
        if result is None:
            self._raise_not_found(collection_id)
        return result

    @staticmethod
    def _raise_not_found(collection_id: str) -> None:
        raise CollectionNotFoundError(
            details={"collection_id": collection_id},
        )

    async def delete(self, collection_id: str) -> int:
        """Delete a collection by UUID.  Returns rows deleted."""
        if await self.get(collection_id, "admin") is None:
            return 0
        return await self._repo.delete_collection(collection_id, accessible_ids=[collection_id])

    async def create_required(self, name: str, metadata: dict[str, Any]) -> CollectionDetails:
        """Create collection metadata and reject an empty repository result."""
        data = await self.create(name, metadata)
        if data is None:
            raise DatabaseOperationError(
                code="collection.create_failed",
                message_key="errors.rag.collection.create_failed",
            )
        return data

    async def get_required(self, collection_id: str) -> CollectionDetails:
        """Resolve an accessible collection or raise the public missing error."""
        data = await self.get(collection_id)
        if data is None:
            self._raise_not_found(collection_id)
        return data

    async def delete_mutable(self, collection_id: str, *, force: bool = False) -> None:
        """Check collection write guards, drop the Milvus table, then delete the metadata.

        The row is what names the table, so it goes last: a drop that fails
        (503) keeps the collection and the delete can be repeated. A collection
        that is missing or not the caller's to administer deletes nothing, as
        before.
        """
        from src.collections.write_guards import (
            ensure_collection_mutable,
            ensure_not_connector_managed_collection,
        )
        from src.documents.service import Collection  # documents imports this module

        if not force:
            await ensure_not_connector_managed_collection(collection_id)
        ensure_collection_mutable(collection_id)
        if await self.get(collection_id, "admin") is None:
            return
        await Collection(collection_id, self.user_id).drop()
        await self.delete(collection_id)

    async def update_mutable(
        self, collection_id: str, *, name: str | None, metadata: dict[str, Any] | None
    ) -> CollectionDetails:
        """Check collection write guards before changing its metadata."""
        from src.collections.write_guards import (
            ensure_collection_mutable,
            ensure_not_connector_managed_collection,
        )

        await ensure_not_connector_managed_collection(collection_id)
        ensure_collection_mutable(collection_id)
        return await self.update(collection_id, name=name, metadata=metadata)
