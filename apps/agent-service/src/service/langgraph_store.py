"""
LangGraph Store singleton.

Provides a global LangGraph BaseStore instance used across the service
for cross-thread long-term memory persistence.

This is separate from service.store.PostgresStore which handles
assistant/thread table management.
"""

__all__ = ["get_langgraph_store", "set_global_langgraph_store"]

_LANGGRAPH_STORE_INSTANCE = None


def set_global_langgraph_store(store) -> None:
    """Set the global LangGraph store instance (called during lifespan startup)."""
    global _LANGGRAPH_STORE_INSTANCE
    _LANGGRAPH_STORE_INSTANCE = store


def get_langgraph_store():
    """Return the global LangGraph store instance."""
    return _LANGGRAPH_STORE_INSTANCE
