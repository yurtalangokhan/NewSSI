"""One canonical default agent for the agents API.

``ServiceMetadata.default_agent`` is adopted verbatim by the SDK client
(``src/client/client.py``), and the ``/{agent_id}/invoke``, ``/{agent_id}/stream``
and ``/history`` defaults are handed straight to the registry. A default that is
neither a registry key nor a built-in recipe key therefore turns into a runtime
``KeyError`` on the first call a client makes without naming an agent.
"""

from __future__ import annotations

import inspect

from agent_composition.application.recipes import get_builtin_recipe
from agents.primitives.constants import DEFAULT_AGENT
from agents.registry.registry import agents
from api.routes.agents_route import invoke, stream
from service.agents.agent_catalog_service import get_default_agent_id


def _is_servable(agent_id: str) -> bool:
    """Whether the registry can resolve ``agent_id`` to an agent."""
    return agent_id in agents or get_builtin_recipe(agent_id) is not None


def test_default_agent_is_a_registered_agent() -> None:
    """The default must name an agent the registry can actually serve."""
    default_agent = get_default_agent_id()

    assert _is_servable(default_agent), (
        f"default agent {default_agent!r} is neither a registry key nor a built-in "
        f"recipe key, so every defaulted /agents call raises KeyError"
    )


def test_default_agent_has_a_single_source() -> None:
    """The service facade must not carry a second value for the same concept."""
    assert get_default_agent_id() == DEFAULT_AGENT


def test_agent_route_defaults_are_servable() -> None:
    """Every handler that defaults ``agent_id`` must default to a servable agent."""
    for handler in (invoke, stream):
        default = inspect.signature(handler).parameters["agent_id"].default

        assert _is_servable(default), (
            f"{handler.__name__} defaults agent_id to unservable {default!r}"
        )
