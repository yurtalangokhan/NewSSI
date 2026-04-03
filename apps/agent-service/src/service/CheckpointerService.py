"""
Checkpointer singleton.

Provides a global checkpointer instance used across the service
for thread-scoped conversation persistence.
"""

__all__ = ["get_checkpointer", "set_global_checkpointer"]

_CHECKPOINTER_INSTANCE = None


def set_global_checkpointer(saver) -> None:
    """Set the global checkpointer instance (called during lifespan startup)."""
    global _CHECKPOINTER_INSTANCE
    _CHECKPOINTER_INSTANCE = saver


def get_checkpointer():
    """Return the global checkpointer instance."""
    return _CHECKPOINTER_INSTANCE
