"""Agent catalog and runtime metadata service.

Provides a clean domain facade over agent registries and composition components,
preventing the API layer from bypassing domain boundaries.
"""

from __future__ import annotations

from typing import Any

from agents.primitives.constants import DEFAULT_AGENT


def get_default_agent_id() -> str:
    """Return the default agent identifier."""
    return DEFAULT_AGENT


def get_all_agent_info() -> list[dict[str, Any]]:
    """Return metadata for all registered agents."""
    from agents import get_all_agent_info as _get_all

    return _get_all()


def get_agent_graph(agent_id: str | None = None) -> Any:
    """Return compiled agent graph for the given agent_id or default."""
    from agents import get_agent as _get

    return _get(agent_id or DEFAULT_AGENT)


def get_agent_or_lazy(assistant_id: str) -> Any:
    """Return agent instance (or lazy loader) for assistant_id."""
    from agents import get_agent_or_lazy as _get_lazy

    return _get_lazy(assistant_id)


def get_composition_catalog(kind: str | None = None) -> dict[str, Any]:
    """Return available composition components filtered by kind."""
    from agent_composition import ComponentKind, list_available

    component_kind: ComponentKind | None = ComponentKind(kind) if kind else None
    return {
        "components": list_available(component_kind),
        "kinds": [k.value for k in ComponentKind],
    }
