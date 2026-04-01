"""Thread domain service - handles conversation threads."""

import logging
from typing import Any

from core.db.repositories import ThreadRepository

logger = logging.getLogger(__name__)


class ThreadService:
    """Service for managing conversation threads."""

    def __init__(self):
        self._repo = ThreadRepository()

    async def create_thread(
        self, thread_id: str | None = None, metadata: dict | None = None
    ) -> dict[str, Any]:
        """Create a new thread."""
        return await self._repo.add_thread({"thread_id": thread_id, "metadata": metadata or {}})

    async def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        """Get a thread by ID."""
        return await self._repo.get_thread(thread_id)

    async def update_thread(self, thread_id: str, metadata: dict) -> dict[str, Any] | None:
        """Update thread metadata."""
        return await self._repo.update_thread(thread_id, metadata)

    async def list_threads(
        self, limit: int = 100, offset: int = 0, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List threads with optional filtering."""
        return await self._repo.list_threads(limit=limit, offset=offset, user_id=user_id)

    async def delete_thread(self, thread_id: str) -> bool:
        """Delete a thread."""
        return await self._repo.delete_thread(thread_id)
