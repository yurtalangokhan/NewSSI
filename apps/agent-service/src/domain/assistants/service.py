"""Assistant domain service - manages assistant configurations."""

import logging
from typing import Any

from core.db.repositories import AssistantRepository

logger = logging.getLogger(__name__)


class AssistantService:
    """Service for managing assistants."""

    def __init__(self):
        self._repo = AssistantRepository()

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
