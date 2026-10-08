from contextlib import AbstractAsyncContextManager

try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
except ImportError:
    AsyncPostgresSaver = None

from memory.long_term import (
    build_compact_memory_context,
    build_memory_context,
    cancel_all_background_tasks,
    extract_and_save_memories,
    extract_memories_for_turn,
    recall_context_for_turn,
    recall_memories,
    save_memories,
)
from memory.memory_flags import resolve_memory_flags
from memory.postgres import get_postgres_saver, get_postgres_store


def initialize_database() -> AbstractAsyncContextManager[AsyncPostgresSaver]:
    """Initialize the canonical database checkpointer (PostgreSQL)."""
    return get_postgres_saver()


def initialize_store():
    """Initialize the canonical store (PostgreSQL store)."""
    return get_postgres_store()


__all__ = ["initialize_database", "initialize_store", "resolve_memory_flags"]
