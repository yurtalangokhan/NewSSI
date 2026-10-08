"""Process-wide runtime resources.

The LangGraph checkpointer and store are opened once during application
startup and handed out by reference for the rest of the process, exactly like
the database engine next door. They carry no business rule, so they belong
beside the other infrastructure rather than in ``service``, where the agent
runtime and ``agent_composition`` had to import upward to reach them.
"""

from __future__ import annotations

from infrastructure.runtime.checkpointer import get_checkpointer, set_global_checkpointer
from infrastructure.runtime.langgraph_store import (
    get_langgraph_store,
    set_global_langgraph_store,
)

__all__ = [
    "get_checkpointer",
    "get_langgraph_store",
    "set_global_checkpointer",
    "set_global_langgraph_store",
]
