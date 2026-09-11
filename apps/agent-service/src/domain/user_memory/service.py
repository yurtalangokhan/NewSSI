"""UserMemoryService — business logic for the user_memory domain.

After Phase 2 migration, all DB persistence goes through user-service
via HTTP. The LangGraph store (LongTermMemoryCache) stays in agent-service
for fast recall performance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.logger import get_logger
from domain.user_memory.cache import LongTermMemoryCache
from service.UserServiceClient import (
    add_facts_to_user,
    create_user_memory,
    delete_all_user_memories,
    delete_user_memory,
    get_current_access_token,
    get_user_memories,
    get_user_memories_for_recall,
    update_user_memory,
)

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class UserMemoryService:
    """Orchestrates HTTP calls to user-service and LangGraph store caching."""

    def __init__(self, cache: LongTermMemoryCache) -> None:
        self.cache = cache

    def _get_token(self) -> str | None:
        return get_current_access_token()

    # ------------------------------------------------------------------
    # Agent runtime: recall
    # ------------------------------------------------------------------

    async def list_for_recall(self, user_id: str) -> list[str]:
        """Return fact strings for injection into system prompt.

        1) Cache hit → return immediately.
        2) Cache miss → load from user-service, warm cache, return.
        """
        cached = await self.cache.get(user_id)
        if cached is not None:
            return cached

        facts = await get_user_memories_for_recall(user_id)
        await self.cache.set(user_id, facts)
        return facts

    # ------------------------------------------------------------------
    # Agent runtime: save (auto-extracted)
    # ------------------------------------------------------------------

    async def add_facts(
        self, user_id: str, contents: list[str], source: str = "auto_extracted"
    ) -> list[dict]:
        """Normalise, dedupe locally, persist via user-service, invalidate cache."""
        if not contents:
            return []

        seen: set[str] = set()
        unique_contents: list[str] = []
        for raw in contents:
            normalised = raw.strip()
            key = normalised.lower()
            if normalised and key not in seen:
                seen.add(key)
                unique_contents.append(normalised)

        created = await add_facts_to_user(user_id, unique_contents, source=source)
        if created:
            await self.cache.invalidate(user_id)
        return created

    # ------------------------------------------------------------------
    # UI: paginated list (always from user-service, no cache)
    # ------------------------------------------------------------------

    async def list_for_ui(self, user_id: str, page: int = 1, page_size: int = 50) -> dict:
        return await get_user_memories(user_id, page=page, page_size=page_size)

    # ------------------------------------------------------------------
    # UI: CRUD operations (manual memories)
    # ------------------------------------------------------------------

    async def create(self, user_id: str, content: str) -> dict:
        row = await create_user_memory(user_id, content.strip())
        await self.cache.invalidate(user_id)
        return row

    async def update(self, memory_id: str, user_id: str, content: str) -> dict | None:
        row = await update_user_memory(memory_id, user_id, content.strip())
        if row:
            await self.cache.invalidate(user_id)
        return row

    async def delete(self, memory_id: str, user_id: str) -> bool:
        deleted = await delete_user_memory(memory_id, user_id)
        if deleted:
            await self.cache.invalidate(user_id)
        return deleted

    async def delete_all(self, user_id: str) -> int:
        count = await delete_all_user_memories(user_id)
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
        _service = UserMemoryService(cache=cache)
    return _service
