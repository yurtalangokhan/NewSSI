"""Pure helpers for the configurable MCP agent.

Extracted from ``agents/configurable_mcp_agent.py`` to reduce its LOC.  All
functions here are stateless and delegate to the canonical long-term memory
trust boundary.
"""

from __future__ import annotations

from typing import Any

from memory.long_term import build_memory_context


def build_compact_memory_context(memories: dict[str, Any]) -> str:
    """Create a bounded, instruction-safe memory block delegating to the canonical trust boundary."""
    return build_memory_context(memories)
