import uuid
from typing import Any

from src.repository import UserMemoryRepository

MAX_FACTS = 50


class UserMemoryService:
    def __init__(self):
        self.repo = UserMemoryRepository()

    async def list_for_recall(self, user_id: uuid.UUID) -> list[str]:
        rows = await self.repo.list_by_user(user_id, limit=MAX_FACTS)
        return [r.content for r in rows]

    async def list_for_ui(
        self, user_id: uuid.UUID, page: int = 1, page_size: int = 50
    ) -> dict[str, Any]:
        rows = await self.repo.list_by_user(user_id)
        total = len(rows)
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "items": [self._memory_to_dict(r) for r in rows[start:end]],
            "total": total,
        }

    async def add_facts(
        self, user_id: uuid.UUID, contents: list[str], source: str = "auto_extracted"
    ) -> list[dict[str, Any]]:
        if not contents:
            return []

        seen: set[str] = set()
        unique_items: list[tuple[str, str]] = []
        for raw in contents:
            normalised = raw.strip()
            key = normalised.lower()
            if normalised and key not in seen:
                seen.add(key)
                unique_items.append((normalised, source))

        created = await self.repo.bulk_create(user_id, unique_items)
        return [self._memory_to_dict(r) for r in created]

    async def create(self, user_id: uuid.UUID, content: str) -> dict[str, Any]:
        row = await self.repo.create(user_id, content.strip(), source="manual")
        return self._memory_to_dict(row)

    async def get(self, memory_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any] | None:
        row = await self.repo.get(memory_id, user_id)
        if not row:
            return None
        return self._memory_to_dict(row)

    async def update(
        self, memory_id: uuid.UUID, user_id: uuid.UUID, content: str
    ) -> dict[str, Any] | None:
        row = await self.repo.update(memory_id, user_id, content.strip())
        if not row:
            return None
        return self._memory_to_dict(row)

    async def delete(self, memory_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        return await self.repo.delete(memory_id, user_id)

    async def delete_all(self, user_id: uuid.UUID) -> int:
        return await self.repo.delete_all(user_id)

    async def count(self, user_id: uuid.UUID) -> int:
        return await self.repo.count(user_id)

    def _memory_to_dict(self, row) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "user_id": str(row.user_id),
            "content": row.content,
            "source": row.source,
            "time_created": row.time_created.isoformat() if row.time_created else None,
            "time_updated": row.time_updated.isoformat() if row.time_updated else None,
        }


_memory_service: UserMemoryService | None = None


def get_user_memory_service() -> UserMemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = UserMemoryService()
    return _memory_service
