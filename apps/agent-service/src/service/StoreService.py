"""
Application Store – thin wrapper around the SQLAlchemy repository layer.

The ``PostgresStore`` class has been replaced by
:class:`~core.db.repositories.AssistantRepository` and
:class:`~core.db.repositories.ThreadRepository`.

This module still exposes the **same public wrapper functions** that the
rest of the service layer uses (``get_assistant_from_store``,
``add_thread``, etc.) so that callers need no changes.  Internally every
function now delegates to the corresponding repository.

``get_store()`` / ``set_global_store()`` are kept for backward
compatibility during the migration period.  New code should import the
repositories directly from ``core.db``.
"""

import logging

from core.db import AssistantRepository, ThreadRepository

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Global singletons (backward compat)
# ------------------------------------------------------------------

_STORE_INSTANCE: object | None = None


def set_global_store(store: object | None = None) -> None:
    """Set the global store instance (kept for lifespan compat)."""
    global _STORE_INSTANCE
    _STORE_INSTANCE = store


def get_store():
    """Return the global store marker.

    .. deprecated::
        New code should use the repository classes directly.
    """
    return _STORE_INSTANCE


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
    return AssistantRepository()


def _thread_repo() -> ThreadRepository:
    return ThreadRepository()


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

async def add_thread(thread: dict):
    await _thread_repo().add_thread(thread)


async def get_thread_from_store(thread_id: str) -> dict | None:
    return await _thread_repo().get_thread(thread_id)


async def list_threads_from_store(
    limit: int = 100, offset: int = 0, metadata: dict | None = None
) -> list[dict]:
    return await _thread_repo().list_threads(
        limit=limit, offset=offset, metadata_filter=metadata
    )


async def update_thread_in_store(
    thread_id: str,
    updates: dict,
    update_timestamp: bool = True,
) -> dict | None:
    return await _thread_repo().update_thread(
        thread_id,
        updates,
        update_timestamp=update_timestamp,
    )


async def delete_thread_from_store(thread_id: str) -> bool:
    return await _thread_repo().delete_thread(thread_id)
