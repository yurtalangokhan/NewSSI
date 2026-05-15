"""LangGraph store cache wrapper for user long-term memories."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph.store.base import BaseStore

logger = logging.getLogger(__name__)

NAMESPACE_PREFIX = "memories"
FACTS_KEY = "user_facts"


class LongTermMemoryCache:
    """Wraps the LangGraph in-process store as a read-through cache.

    Canonical source of truth is the ``user_memory`` DB table.
    The store holds a warm copy for fast in-process recall.
    """

    def __init__(self, store: "BaseStore") -> None:
        self._store = store

    def _namespace(self, user_id: str) -> tuple[str, str]:
        return (NAMESPACE_PREFIX, user_id)

    async def get(self, user_id: str) -> list[str] | None:
        """Return cached facts or None on cache miss."""
        if not self._store or not user_id:
            return None
        try:
            result = await self._store.aget(self._namespace(user_id), key=FACTS_KEY)
            if result and hasattr(result, "value") and result.value:
                return result.value.get("facts", [])
        except Exception as e:
            logger.debug(f"[LTMCache] get failed for {user_id}: {e}")
        return None

    async def set(self, user_id: str, contents: list[str]) -> None:
        """Overwrite the cache with a fresh list of fact strings."""
        if not self._store or not user_id:
            return
        try:
            from datetime import UTC, datetime

            await self._store.aput(
                self._namespace(user_id),
                key=FACTS_KEY,
                value={
                    "facts": contents,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )
        except Exception as e:
            logger.debug(f"[LTMCache] set failed for {user_id}: {e}")

    async def invalidate(self, user_id: str) -> None:
        """Remove the user's cache entry so the next recall hits the DB."""
        if not self._store or not user_id:
            return
        try:
            await self._store.adelete(self._namespace(user_id), key=FACTS_KEY)
        except Exception as e:
            logger.debug(f"[LTMCache] invalidate failed for {user_id}: {e}")
