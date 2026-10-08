"""Thread domain service - handles conversation threads."""

from __future__ import annotations

from typing import Any, Protocol

from core.observability.logger import get_logger
from schemas.threads import ThreadEntity

logger = get_logger(__name__)


class ThreadRepositoryPort(Protocol):
    """Persistence port for threads.

    Implemented by the concrete repository in ``infrastructure.db.repositories``. The
    domain depends on this abstraction, never on the infrastructure class, so
    the dependency direction points inward (clean architecture).
    """

    async def add_thread(self, data: dict[str, Any]) -> dict[str, Any] | None: ...

    async def get_thread(self, thread_id: str) -> dict[str, Any] | None: ...

    async def update_thread(self, thread_id: str, metadata: dict[str, Any]) -> dict[str, Any] | None: ...

    async def list_threads(
        self, limit: int = 100, offset: int = 0, user_id: str | None = None
    ) -> list[dict[str, Any]]: ...

    async def delete_thread(self, thread_id: str) -> bool: ...


class ThreadService:
    """Service for managing conversation threads."""

    def __init__(self, repo: ThreadRepositoryPort | None = None) -> None:
        if repo is None:
            from infrastructure.db.persistence_gateway import thread_repository

            repo = thread_repository()
        self._repo = repo

    async def create_thread(self, thread_id: str | None = None, metadata: dict | None = None) -> ThreadEntity | None:
        """Create a new thread."""
        res = await self._repo.add_thread({"thread_id": thread_id, "metadata": metadata or {}})
        return ThreadEntity.model_validate(res) if res else None

    async def get_thread(self, thread_id: str) -> ThreadEntity | None:
        """Get a thread by ID."""
        res = await self._repo.get_thread(thread_id)
        return ThreadEntity.model_validate(res) if res else None

    async def update_thread(self, thread_id: str, metadata: dict) -> ThreadEntity | None:
        """Update thread metadata."""
        res = await self._repo.update_thread(thread_id, metadata)
        return ThreadEntity.model_validate(res) if res else None

    async def list_threads(self, limit: int = 100, offset: int = 0, user_id: str | None = None) -> list[ThreadEntity]:
        """List threads with optional filtering."""
        rows = await self._repo.list_threads(limit=limit, offset=offset, user_id=user_id)
        return [ThreadEntity.model_validate(r) if not isinstance(r, ThreadEntity) else r for r in rows]

    async def delete_thread(self, thread_id: str) -> bool:
        """Delete a thread."""
        return await self._repo.delete_thread(thread_id)
