"""
Application Store - the service layer's single door to the thread and assistant tables.

The ``PostgresStore`` class has been replaced by
:class:`~infrastructure.db.repositories.AssistantRepository` and
:class:`~infrastructure.db.repositories.ThreadRepository`.

This module exposes the **public wrapper functions** every other service uses
(``get_assistant_from_store``, ``add_thread``, ``delete_threads_older_than``,
…) so that threads and assistants have exactly one access path in the service
layer. The repositories are named here and nowhere else:
``tests/core/test_repository_style.py`` enforces both halves of that — that no
other service module names them, and that this door carries every operation its
callers need (an incomplete door is what pushes a caller back to the
repository). Services that own a different table should still use their own
repository, or ``core.persistence_gateway``.

``get_store()`` / ``set_global_store()`` are kept for backward
compatibility during the migration period.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING

from core.observability.logger import get_logger
from infrastructure.db.persistence_gateway import assistant_repository, thread_repository
from schemas.threads import ThreadEntity

if TYPE_CHECKING:
    # Type only: the repository itself comes from the gateway at
    # runtime, so the class is never reachable here.
    from infrastructure.db.repositories import (
        AssistantRepository,
        ThreadRepository,
    )


logger = get_logger(__name__)

# ------------------------------------------------------------------
# Checkpointer (unchanged — LangGraph still owns these)
# ------------------------------------------------------------------

_CHECKPOINTER_INSTANCE = None


def set_global_checkpointer(checkpointer):
    """Set the global checkpointer instance."""
    global _CHECKPOINTER_INSTANCE
    _CHECKPOINTER_INSTANCE = checkpointer


def get_checkpointer():
    """Get the global checkpointer instance."""
    return _CHECKPOINTER_INSTANCE


# ------------------------------------------------------------------
# Lazy repository singletons
# ------------------------------------------------------------------


def _assistant_repo() -> AssistantRepository:
    return assistant_repository()


def _thread_repo() -> ThreadRepository:
    return thread_repository()


# ------------------------------------------------------------------
# Assistant wrapper functions
# ------------------------------------------------------------------


async def load_assistants_store_async() -> dict[str, dict]:
    assistants = await _assistant_repo().list_assistants()
    return {a["assistant_id"]: a for a in assistants}


async def save_assistant_async(assistant: dict):
    await _assistant_repo().save_assistant(assistant)


async def get_assistant_from_store(assistant_id: str) -> dict | None:
    return await _assistant_repo().get_assistant(assistant_id)


async def list_assistants_from_store() -> list[dict]:
    return await _assistant_repo().list_assistants()


async def update_assistant_in_store(assistant_id: str, updates: dict) -> dict | None:
    return await _assistant_repo().update_assistant(assistant_id, updates)


async def delete_assistant_from_store(assistant_id: str) -> bool:
    return await _assistant_repo().delete_assistant(assistant_id)


# ------------------------------------------------------------------
# Thread wrapper functions
# ------------------------------------------------------------------


async def add_thread(thread: dict) -> ThreadEntity | None:
    res = await _thread_repo().add_thread(thread)
    return ThreadEntity.model_validate(res) if res else None


async def get_thread_from_store(thread_id: str) -> ThreadEntity | None:
    res = await _thread_repo().get_thread(thread_id)
    return ThreadEntity.model_validate(res) if res else None


async def list_threads_from_store(
    limit: int = 100,
    offset: int = 0,
    metadata: dict | None = None,
    metadata_any: Sequence[dict] | None = None,
    run_kinds: Sequence[str] | None = None,
) -> list[ThreadEntity]:
    rows = await _thread_repo().list_threads(
        limit=limit,
        offset=offset,
        metadata_filter=metadata,
        metadata_filter_any=metadata_any,
        run_kinds=run_kinds,
    )
    return [ThreadEntity.model_validate(r) if not isinstance(r, ThreadEntity) else r for r in rows]


async def list_chat_sessions_by_activity_from_store(
    page_size: int = 100,
    before_activity: str | None = None,
    before_id: str | None = None,
    metadata: dict | None = None,
    metadata_any: Sequence[dict] | None = None,
    run_kinds: Sequence[str] | None = None,
    name_contains: str | None = None,
    agents_only: bool = False,
) -> list[ThreadEntity]:
    """List chat threads using the dedicated conversational activity order."""
    rows = await _thread_repo().list_chat_sessions_by_activity(
        page_size=page_size,
        before_activity=before_activity,
        before_id=before_id,
        metadata_filter=metadata,
        metadata_filter_any=metadata_any,
        run_kinds=run_kinds,
        name_contains=name_contains,
        agents_only=agents_only,
    )
    return [ThreadEntity.model_validate(r) if not isinstance(r, ThreadEntity) else r for r in rows]


async def update_thread_in_store(
    thread_id: str,
    updates: dict,
    update_timestamp: bool = True,
) -> ThreadEntity | None:
    res = await _thread_repo().update_thread(
        thread_id,
        updates,
        update_timestamp=update_timestamp,
    )
    return ThreadEntity.model_validate(res) if res else None


async def mark_thread_message_activity(thread_id: str, *, at: datetime | None = None) -> ThreadEntity | None:
    """Record message activity for a thread: now, or a given earlier instant."""
    res = await _thread_repo().mark_message_activity(thread_id, at=at)
    return ThreadEntity.model_validate(res) if res else None


async def mark_thread_accessed(thread_id: str) -> ThreadEntity | None:
    """Record a read of a thread without mutating its message activity."""
    res = await _thread_repo().mark_accessed(thread_id)
    return ThreadEntity.model_validate(res) if res else None


async def delete_thread_from_store(thread_id: str) -> bool:
    return await _thread_repo().delete_thread(thread_id)


async def delete_threads_older_than(run_kind: str, older_than: datetime) -> list[str]:
    """Bulk-delete threads of one run kind created before ``older_than``.

    Returns the deleted thread_ids. Exposed here so retention (and anything else
    that prunes threads) has no reason to reach for ``ThreadRepository`` itself:
    ``tests/core/test_repository_style.py`` keeps this module the only place in
    the service layer that names the thread/assistant repositories.
    """
    return await _thread_repo().delete_threads_older_than(
        run_kind=run_kind,
        older_than=older_than,
    )


async def delete_threads_inactive_since(run_kind: str, older_than: datetime) -> list[str]:
    """Bulk-delete threads of one run kind with no activity since ``older_than``.

    The inactivity counterpart of ``delete_threads_older_than``: production
    threads age out on last use, not on creation date, so a conversation
    someone still returns to is not deleted for being old.
    """
    return await _thread_repo().delete_threads_inactive_since(
        run_kind=run_kind,
        older_than=older_than,
    )
