from typing import Any
import uuid

from config_manager import env
from error_contract import BadRequestError, MemoryNotFoundError

from src.client import rag_memory_client
from src.core.background_tasks import spawn_tracked
from src.core.observability import get_logger
from src.repository import UserMemoryRepository

logger = get_logger(__name__)


class UserMemoryService:
    @staticmethod
    def _content(content: str) -> str:
        content = content.strip()
        if not content:
            raise BadRequestError(message_key="errors.user_service.memory.content_required")
        return content

    def __init__(self):
        self.repo = UserMemoryRepository()

    def _sync_upsert(self, user_id: uuid.UUID, fact_id: uuid.UUID, content: str) -> None:
        """Fire-and-forget: keep rag-service's semantic index in sync.

        Never awaited by the caller -- a Milvus/rag-service hiccup must not
        fail the user-facing CRUD request that triggered this.
        """

        async def _run() -> None:
            try:
                await rag_memory_client.upsert_fact(user_id=str(user_id), fact_id=str(fact_id), content=content)
            except Exception as exc:
                logger.warning("Failed to sync memory fact %s to rag-service: %s", fact_id, exc)

        spawn_tracked(_run())

    def _sync_delete(self, user_id: uuid.UUID, fact_id: uuid.UUID) -> None:
        async def _run() -> None:
            try:
                await rag_memory_client.delete_fact(user_id=str(user_id), fact_id=str(fact_id))
            except Exception as exc:
                logger.warning("Failed to sync memory fact deletion %s to rag-service: %s", fact_id, exc)

        spawn_tracked(_run())

    def _sync_delete_all(self, user_id: uuid.UUID) -> None:
        async def _run() -> None:
            try:
                await rag_memory_client.delete_all_facts(user_id=str(user_id))
            except Exception as exc:
                logger.warning(
                    "Failed to sync memory delete-all for user %s to rag-service: %s",
                    user_id,
                    exc,
                )

        spawn_tracked(_run())

    async def list_for_recall(self, user_id: uuid.UUID) -> list[str]:
        rows = await self.repo.list_by_user(user_id, limit=env.MEMORY_MAX_FACTS)
        return [r.content for r in rows]

    async def list_for_ui(self, user_id: uuid.UUID, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        """Paginate at the database level.

        The previous version fetched every one of the user's facts
        (repo.list_by_user(user_id), no limit/offset) and sliced the
        Python list -- every page request re-fetched the whole table
        regardless of page_size (spec T4).
        """
        offset = (page - 1) * page_size
        rows = await self.repo.list_by_user(user_id, limit=page_size, offset=offset)
        total = await self.repo.count(user_id)
        return {
            "items": [self._memory_to_dict(r) for r in rows],
            "total": total,
        }

    async def add_facts(
        self,
        user_id: uuid.UUID,
        contents: list[str],
        source: str = "auto_extracted",
        language: str | None = None,
    ) -> list[dict[str, Any]]:
        """Persist a batch of extracted facts.

        `language` is the BCP-47 tag agent-service's extractor had the model
        declare for this conversation -- one tag per batch, not per fact.
        Blank or missing becomes NULL rather than an empty string: the column
        distinguishes "no language was declared" from any declared language,
        and "" would be a third state meaning the same thing.
        """
        if not contents:
            return []

        declared_language = (language or "").strip() or None

        seen: set[str] = set()
        unique_items: list[tuple[str, str, str | None]] = []
        for raw in contents:
            normalised = raw.strip()
            key = normalised.lower()
            if normalised and key not in seen:
                seen.add(key)
                unique_items.append((normalised, source, declared_language))

        created = await self.repo.bulk_create(user_id, unique_items)
        if created:
            # Bound storage at write time, not just at recall time -- without
            # this, only list_for_recall's LIMIT capped what was read back;
            # nothing ever removed old rows, so the table grew forever.
            await self.repo.delete_oldest_excess(user_id, keep=env.MEMORY_MAX_FACTS)
            for row in created:
                self._sync_upsert(user_id, row.id, row.content)
        return [self._memory_to_dict(r) for r in created]

    async def create(self, user_id: uuid.UUID, content: str) -> dict[str, Any]:
        content = self._content(content)
        row = await self.repo.create(user_id, content, source="manual")
        self._sync_upsert(user_id, row.id, row.content)
        return self._memory_to_dict(row)

    async def get(self, memory_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any]:
        row = await self.repo.get(memory_id, user_id)
        if not row:
            raise MemoryNotFoundError()
        return self._memory_to_dict(row)

    async def update(self, memory_id: uuid.UUID, user_id: uuid.UUID, content: str) -> dict[str, Any]:
        content = self._content(content)
        row = await self.repo.update(memory_id, user_id, content)
        if not row:
            raise MemoryNotFoundError()
        self._sync_upsert(user_id, row.id, row.content)
        return self._memory_to_dict(row)

    async def delete(self, memory_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        deleted = await self.repo.delete(memory_id, user_id)
        if not deleted:
            raise MemoryNotFoundError()
        self._sync_delete(user_id, memory_id)
        return deleted

    async def delete_all(self, user_id: uuid.UUID) -> int:
        count = await self.repo.delete_all(user_id)
        if count:
            self._sync_delete_all(user_id)
        return count

    async def count(self, user_id: uuid.UUID) -> int:
        return await self.repo.count(user_id)

    def _memory_to_dict(self, row) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "user_id": str(row.user_id),
            "content": row.content,
            "source": row.source,
            "language": row.language,
            "time_created": row.time_created.isoformat() if row.time_created else None,
            "time_updated": row.time_updated.isoformat() if row.time_updated else None,
        }


_memory_service: UserMemoryService | None = None


def get_user_memory_service() -> UserMemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = UserMemoryService()
    return _memory_service
