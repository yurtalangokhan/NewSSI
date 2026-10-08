"""Pure helpers for assistant routes.

Extracted from ``assistants_route`` to keep the route file focused on endpoint
definitions. All functions here are stateless.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def agent_to_assistant(agent_id: str, agent_description: str) -> dict[str, Any]:
    """Convert an agent to LangGraph Assistant format."""
    now = datetime.now(UTC).isoformat()
    return {
        "assistant_id": agent_id,
        "graph_id": agent_id,
        "name": agent_id,
        "config": {},
        "metadata": {
            "description": agent_description,
            "_x_oap_is_default": True,
        },
        "created_at": now,
        "updated_at": now,
        "version": 1,
    }
