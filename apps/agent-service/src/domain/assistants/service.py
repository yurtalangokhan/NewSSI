"""Assistant domain service - manages assistant configurations."""

from __future__ import annotations

from typing import Any, Protocol

from core.logger import get_logger

logger = get_logger(__name__)


class AssistantRepositoryPort(Protocol):
    """Persistence port for assistants.

    Implemented by the concrete repository in ``core.db.repositories``. The
    domain depends on this abstraction, never on the infrastructure class, so
    the dependency direction points inward (clean architecture).
    """

    async def save_assistant(self, data: dict[str, Any]) -> dict[str, Any]: ...

    async def get_assistant(self, assistant_id: str) -> dict[str, Any] | None: ...

    async def update_assistant(
        self, assistant_id: str, updates: dict[str, Any]
    ) -> dict[str, Any] | None: ...

    async def list_assistants(self) -> list[dict[str, Any]]: ...

    async def delete_assistant(self, assistant_id: str) -> bool: ...


class AssistantService:
    """Service for managing assistants."""

    def __init__(self, repo: AssistantRepositoryPort) -> None:
        self._repo = repo

    async def create_assistant(
        self,
        graph_id: str,
        name: str | None = None,
        config: dict | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Create a new assistant."""
        import uuid

        assistant_id = str(uuid.uuid4())
        return await self._repo.save_assistant(
            {
                "assistant_id": assistant_id,
                "graph_id": graph_id,
                "name": name,
                "config": config or {},
                "metadata": metadata or {},
            }
        )

    async def get_assistant(self, assistant_id: str) -> dict[str, Any] | None:
        """Get an assistant by ID."""
        return await self._repo.get_assistant(assistant_id)

    async def update_assistant(
        self,
        assistant_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update an assistant."""
        return await self._repo.update_assistant(assistant_id, updates)

    async def list_assistants(self) -> list[dict[str, Any]]:
        """List all assistants."""
        return await self._repo.list_assistants()

    async def delete_assistant(self, assistant_id: str) -> bool:
        """Delete an assistant."""
        return await self._repo.delete_assistant(assistant_id)
