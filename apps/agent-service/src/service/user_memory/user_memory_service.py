"""UserMemoryService — business logic for the user_memory domain.

All persistence goes through user-service via HTTP, which is also what
keeps rag-service's semantic-search index in sync on every write. Recall
no longer runs through this service or any agent-service-side cache: it's
query-aware semantic search against rag-service directly (see
memory.long_term.recall_memories). Manual fact CRUD is served by
user-service's own public /users/me/memories API, not proxied through
agent-service. This service's only remaining job is persisting
auto-extracted facts.
"""

from __future__ import annotations

from typing import Any

from core.observability.logger import get_logger
from integrations.user_service_client import add_facts_to_user

logger = get_logger(__name__)


class UserMemoryService:
    """Persists auto-extracted facts via user-service."""

    async def add_facts(
        self,
        user_id: str,
        contents: list[str],
        source: str = "auto_extracted",
        language: str = "",
    ) -> list[dict[str, Any]]:
        """Normalise, dedupe locally, and persist via user-service.

        `language` is the BCP-47 tag the extractor's model declared for this
        batch. It travels with the facts so a wrong-language fact -- which
        recall can never match and therefore never surfaces -- is detectable
        after the fact instead of silently unreachable.
        """
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

        return await add_facts_to_user(user_id, unique_contents, source=source, language=language)


# ---------------------------------------------------------------------------
# DI singleton factory
# ---------------------------------------------------------------------------

_service: UserMemoryService | None = None


def get_user_memory_service() -> UserMemoryService:
    """Return the singleton UserMemoryService."""
    global _service
    if _service is None:
        _service = UserMemoryService()
    return _service
