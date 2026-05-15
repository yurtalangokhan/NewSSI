"""UserMemoryService — business logic for the user_memory domain."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.db.models.user_memory import UserMemoryModel
from core.db.repositories.UserMemoryRepository import UserMemoryRepository
from domain.user_memory.cache import LongTermMemoryCache

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

MAX_FACTS = 50  # hard cap per user


class UserMemoryService:
    """Orchestrates DB persistence and LangGraph store caching for user memories."""

    def __init__(self, repo: UserMemoryRepository, cache: LongTermMemoryCache) -> None:
        self.repo = repo
        self.cache = cache

    # ------------------------------------------------------------------
    # Agent runtime: recall
    # ------------------------------------------------------------------

    async def list_for_recall(self, user_id: str) -> list[str]:
        """Return fact strings for injection into system prompt.

        1) Cache hit → return immediately.
        2) Cache miss → load from DB, warm cache, return.
        """
        cached = await self.cache.get(user_id)
        if cached is not None:
            return cached

        rows = await self.repo.list_by_user(user_id, limit=MAX_FACTS)
        facts = [r.content for r in rows]
        await self.cache.set(user_id, facts)
        return facts

    # ------------------------------------------------------------------
    # Agent runtime: save (auto-extracted)
    # ------------------------------------------------------------------

    async def add_facts(
        self, user_id: str, contents: list[str], source: str = "auto_extracted"
    ) -> list[UserMemoryModel]:
        """Normalise, dedupe, persist, and invalidate cache."""
        if not contents:
            return []

        # Local dedupe before hitting DB
        seen: set[str] = set()
        unique_items: list[tuple[str, str]] = []
        for raw in contents:
            normalised = raw.strip()
            key = normalised.lower()
            if normalised and key not in seen:
                seen.add(key)
                unique_items.append((normalised, source))

        created = await self.repo.bulk_create(user_id, unique_items)
        if created:
            await self.cache.invalidate(user_id)
        return created

    # ------------------------------------------------------------------
    # UI: paginated list (always from DB, no cache)
    # ------------------------------------------------------------------

    async def list_for_ui(
        self, user_id: str, page: int = 1, page_size: int = 50
    ) -> dict:
        """Return a paginated list for the settings UI."""
        rows = await self.repo.list_by_user(user_id)
        total = len(rows)
        start = (page - 1) * page_size
        end = start + page_size
        return {"items": rows[start:end], "total": total}

    # ------------------------------------------------------------------
    # UI: CRUD operations (manual memories)
    # ------------------------------------------------------------------

    async def create(self, user_id: str, content: str) -> UserMemoryModel:
        row = await self.repo.create(user_id, content.strip(), source="manual")
        await self.cache.invalidate(user_id)
        return row

    async def update(
        self, memory_id: str, user_id: str, content: str
    ) -> UserMemoryModel | None:
        row = await self.repo.update(memory_id, user_id, content.strip())
        if row:
            await self.cache.invalidate(user_id)
        return row

    async def delete(self, memory_id: str, user_id: str) -> bool:
        deleted = await self.repo.delete(memory_id, user_id)
        if deleted:
            await self.cache.invalidate(user_id)
        return deleted

    async def delete_all(self, user_id: str) -> int:
        count = await self.repo.delete_all(user_id)
        if count:
            await self.cache.invalidate(user_id)
        return count


# ---------------------------------------------------------------------------
# DI singleton factory
# ---------------------------------------------------------------------------

_service: UserMemoryService | None = None


def get_user_memory_service() -> UserMemoryService:
    """Return the singleton UserMemoryService.

    The LangGraph store is resolved lazily so this can be called before the
    lifespan hook finishes.
    """
    global _service
    if _service is None:
        from service.LangGraphStoreService import get_langgraph_store

        store = get_langgraph_store()
        cache = LongTermMemoryCache(store)
        repo = UserMemoryRepository()
        _service = UserMemoryService(repo=repo, cache=cache)
    return _service
