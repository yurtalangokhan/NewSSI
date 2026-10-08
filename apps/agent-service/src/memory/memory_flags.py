"""Resolve the long-term-memory gates for a run's RunnableConfig.

The user's personalization settings are the master switch:

* ``long_term_memory_enabled`` ("Depolanan Belleğe Başvur") gates recall
  *and* is the primary gate for saving.
* ``extract_memory`` ("Belleği Güncelle") gates the LLM fact-extraction /
  save step. It is meaningless while recall is off, so it collapses to
  ``False`` in that case.

An agent only participates in long-term memory when it is a default
assistant / plain model chatbot (the user setting is then the sole
driver) or when its own configuration opts in. See callers for how
``agent_participates`` is derived.
"""

from __future__ import annotations

__all__ = ["resolve_memory_flags"]


def resolve_memory_flags(
    *,
    user_recall_enabled: bool,
    user_extract_enabled: bool,
    agent_participates: bool,
    agent_extract_allowed: bool = True,
) -> tuple[bool, bool]:
    """Return ``(long_term_memory, extract_memory)`` for ``configurable``.

    Args:
        user_recall_enabled: User setting "Depolanan Belleğe Başvur".
        user_extract_enabled: User setting "Belleği Güncelle".
        agent_participates: Whether this agent may use long-term memory at all.
        agent_extract_allowed: Agent-level extract label (defaults to allowed).

    ``long_term_memory`` gates recall and is the primary save gate in the
    agent nodes; ``extract_memory`` is the secondary save gate. Because both
    depend on ``long_term_memory``, turning the user's recall setting off
    disables recall *and* save.
    """
    long_term_memory = bool(user_recall_enabled and agent_participates)
    extract_memory = bool(long_term_memory and user_extract_enabled and agent_extract_allowed)
    return long_term_memory, extract_memory
