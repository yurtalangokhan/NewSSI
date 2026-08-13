import uuid

from src.service import get_user_memory_service

from .base import BaseController


class UserMemoryController(BaseController):
    def __init__(self):
        self.service = get_user_memory_service()

    async def list_memories(self, user_id: uuid.UUID, page: int = 1, page_size: int = 50) -> dict:
        return await self.service.list_for_ui(user_id, page=page, page_size=page_size)

    async def list_for_recall(self, user_id: uuid.UUID) -> list[str]:
        return await self.service.list_for_recall(user_id)

    async def create_memory(self, user_id: uuid.UUID, content: str) -> dict:
        try:
            return await self.service.create(user_id, content)
        except Exception:
            self._raise_conflict("memory.already_exists")

    async def add_facts(
        self, user_id: uuid.UUID, contents: list[str], source: str = "auto_extracted"
    ) -> list[dict]:
        return await self.service.add_facts(user_id, contents, source=source)

    async def update_memory(self, user_id: uuid.UUID, memory_id: uuid.UUID, content: str) -> dict:
        result = await self.service.update(memory_id, user_id, content)
        if not result:
            self._raise_not_found("memory.not_found")
        return result

    async def delete_memory(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> None:
        deleted = await self.service.delete(memory_id, user_id)
        if not deleted:
            self._raise_not_found("memory.not_found")

    async def delete_all_memories(self, user_id: uuid.UUID) -> dict:
        count = await self.service.delete_all(user_id)
        return {"deleted": count}

    async def get_memory(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> dict:
        result = await self.service.get(memory_id, user_id)
        if not result:
            self._raise_not_found("memory.not_found")
        return result


_memory_controller: UserMemoryController | None = None


def get_user_memory_controller() -> UserMemoryController:
    global _memory_controller
    if _memory_controller is None:
        _memory_controller = UserMemoryController()
    return _memory_controller
