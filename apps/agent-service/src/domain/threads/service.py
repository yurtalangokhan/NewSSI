"""Thread domain service - handles conversation threads."""

from __future__ import annotations

from typing import Any, Protocol

from core.logger import get_logger

logger = get_logger(__name__)


class ThreadRepositoryPort(Protocol):
    """Persistence port for threads.

    Implemented by the concrete repository in ``core.db.repositories``. The
    domain depends on this abstraction, never on the infrastructure class, so
    the dependency direction points inward (clean architecture).
    """

    async def add_thread(self, data: dict[str, Any]) -> dict[str, Any]: ...

    async def get_thread(self, thread_id: str) -> dict[str, Any] | None: ...

    async def update_thread(
        self, thread_id: str, metadata: dict[str, Any]
    ) -> dict[str, Any] | None: ...

    async def list_threads(
        self, limit: int = 100, offset: int = 0, user_id: str | None = None
    ) -> list[dict[str, Any]]: ...

    async def delete_thread(self, thread_id: str) -> bool: ...


class ThreadService:
    """Service for managing conversation threads."""

    def __init__(self, repo: ThreadRepositoryPort) -> None:
        self._repo = repo

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
