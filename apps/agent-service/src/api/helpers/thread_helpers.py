"""Pure helpers for thread routes.

Extracted from ``threads_route`` to keep the route file focused on endpoint
definitions.
"""

from __future__ import annotations

from typing import Any


def sanitize_checkpoint_values(values: dict[str, Any]) -> dict[str, Any]:
    """Remove non-serializable types like Send from checkpoint values."""
    from langgraph.types import Send

    sanitized: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, Send):
            sanitized[key] = {
                "__type__": "Send",
                "node": value.node,
                "arg": str(value.arg)[:500],
            }
        elif isinstance(value, dict):
            sanitized[key] = sanitize_checkpoint_values(value)
        elif isinstance(value, list):
            sanitized[key] = [
                {
                    "__type__": "Send",
                    "node": v.node,
                    "arg": str(v.arg)[:500],
                }
                if isinstance(v, Send)
                else (sanitize_checkpoint_values(v) if isinstance(v, dict) else v)
                for v in value
            ]
        else:
            sanitized[key] = value
    return sanitized
