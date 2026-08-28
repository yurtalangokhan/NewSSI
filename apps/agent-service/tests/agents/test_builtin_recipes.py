"""Tests for built-in agent recipes and the recipe-aware resolver.

These lock the ASC-6 behavior:

* Built-in recipe keys map to ``AgentFactory``-compatible definition configs.
* Recipe-only built-ins (``pipeline``, ``supervisor``) resolve through
  ``AgentFactory.create`` (the same composer used by persisted dynamic agents).
* The legacy static registry (``chatbot``, ``configurable-mcp-agent``) is still
  served from the static registry for backward compatibility.
"""

from __future__ import annotations

import pytest

from agent_composition.application.compose_agent import AgentFactory
from agent_composition.application.recipes import (
    get_builtin_recipe,
    list_builtin_recipe_keys,
)


class FakeGateway:
    """Minimal in-memory ToolGateway stand-in (no network)."""

    async def load(self) -> None:
        return None

    async def describe(self):
        return []

    async def resolve(self, keys):
        return []


@pytest.fixture
def fake_graph_builder(monkeypatch):
    """Replace the real graph builder / model resolution with test doubles."""

    class FakeGraph:
        pass

    class FakeBuilder:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def build_async(self, schema_type, config):
            return FakeGraph()

        def build(self, *_args, **_kwargs):
            raise AssertionError("DynamicAgent.load should not use sync build")

    monkeypatch.setattr("agents.dynamic_agent.GraphBuilder", FakeBuilder)
    monkeypatch.setattr("agents.dynamic_agent.get_model_from_config", lambda *a, **k: object())
    # Avoid any real network gateway when the resolver builds without one.
    monkeypatch.setattr("agents.dynamic_agent._build_default_gateway", lambda: FakeGateway())
    return FakeGraph


def test_recipe_registry_contains_builtins():
    keys = set(list_builtin_recipe_keys())
    assert {"chatbot", "configurable-mcp-agent", "pipeline", "supervisor"}.issubset(keys)
    for key in keys:
        recipe = get_builtin_recipe(key)
        assert recipe is not None
        assert "name" in recipe
        assert "graph_schema" in recipe


def test_builtin_recipes_do_not_pin_a_model():
    """Built-in recipes must let runtime provider defaults choose the model."""
    for key in list_builtin_recipe_keys():
        recipe = get_builtin_recipe(key)
        assert recipe is not None
        assert "model" not in recipe, f"{key} must not hardcode a model"

        nested_configs = recipe.get("sub_agents", []) + recipe.get("stages", [])
        for nested in nested_configs:
            assert "model" not in nested, f"{key} nested config must not hardcode a model"


@pytest.mark.asyncio
async def test_builtin_recipes_resolve_through_factory(fake_graph_builder):
    """Each built-in recipe composes via AgentFactory without raising."""
    for key in ["pipeline", "supervisor", "chatbot", "configurable-mcp-agent"]:
        recipe = get_builtin_recipe(key)
        agent = await AgentFactory.create(recipe, gateway=FakeGateway())
        assert agent is not None
        # AgentFactory.create returns a loaded runtime.
        assert getattr(agent, "_loaded", False) is True


@pytest.mark.asyncio
async def test_resolver_routes_recipe_through_composer(fake_graph_builder):
    """load_agent for a recipe-only key composes via AgentFactory."""
    from agents.agents import agents, get_agent, load_agent

    # Sanity: pipeline is not part of the legacy static registry.
    assert "pipeline" not in agents

    await load_agent("pipeline")

    assert "pipeline" in agents
    # get_agent returns the composed graph (loaded DynamicAgent facade).
    graph = get_agent("pipeline")
    assert graph is not None


@pytest.mark.asyncio
async def test_resolver_keeps_static_registry_for_backward_compat(fake_graph_builder):
    """chatbot remains served from the static registry (no composer routing)."""
    from agents.agents import agents, load_agent

    # chatbot is present in the static registry and must stay there.
    assert "chatbot" in agents
    # Should not raise and should not require the composer path.
    await load_agent("chatbot")
    assert "chatbot" in agents


@pytest.mark.asyncio
async def test_resolver_unknown_key_raises_key_error(fake_graph_builder):
    from agents.agents import load_agent

    with pytest.raises(KeyError):
        await load_agent("does-not-exist")


@pytest.mark.asyncio
async def test_legacy_chatbot_agent_does_not_pin_a_default_model(monkeypatch):
    """The retained legacy agent path must also defer to the runtime default."""
    from agents.impl import chatbot as chatbot_module

    captured: dict[str, object] = {}

    class FakeBrain:
        def __init__(self, *, config, system_prompt):
            captured["brain_config"] = config
            captured["system_prompt"] = system_prompt

        async def load(self):
            return None

    class FakePerceptron:
        def __init__(self, *, config):
            captured["perceptron_config"] = config

        async def load(self):
            return None

    monkeypatch.setattr(chatbot_module, "LLMBrain", FakeBrain)
    monkeypatch.setattr(chatbot_module, "MemoryPerceptron", FakePerceptron)
    monkeypatch.setattr(chatbot_module.ChatbotAgent, "_build_graph", lambda self: object())

    agent = chatbot_module.ChatbotAgent()
    await agent.load()

    assert captured["brain_config"] == {"temperature": 0.7}
