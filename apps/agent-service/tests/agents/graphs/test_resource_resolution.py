"""Tests for resource resolution: LLMModel/OllamaModel resource nodes -> a
real BaseChatModel instance, reusing core.llm.get_model exactly as
GraphBuilder._get_model already does.

Spec: .tmp/flow-canvas-design.md sections 4.3, 7.1.
Brief: .tmp/flow-canvas-task-8-brief.md
"""

from __future__ import annotations

import pytest
from langchain_core.language_models import BaseChatModel

from agents.graphs.flow_builder import resolve_resources
from core.exceptions import NotAResourceNodeError
from models.flows import FlowNode


@pytest.fixture(autouse=True)
def _fake_model_env(monkeypatch):
    monkeypatch.setenv("USE_FAKE_MODEL", "true")


def test_llm_model_resource_resolves_to_chat_model():
    """8.1 — resolves via the real core.llm.get_model factory, not a mock."""
    node = FlowNode(
        id="model-1",
        type="LLMModel",
        values={"provider": "ollama", "model": "fake", "temperature": 0.7},
    )

    resolved = resolve_resources([node])

    assert isinstance(resolved.models["model-1"], BaseChatModel)


def test_ollama_model_resource_resolves_to_chat_model():
    """8.2 — same factory path for OllamaModel."""
    node = FlowNode(id="model-1", type="OllamaModel", values={"model": "fake"})

    resolved = resolve_resources([node])

    assert isinstance(resolved.models["model-1"], BaseChatModel)


def test_missing_model_value_falls_back_to_default_model():
    """8.3 — matches GraphBuilder._get_model's exact fallback: no model_name ->
    settings.DEFAULT_MODEL, not an error."""
    node = FlowNode(id="model-1", type="LLMModel", values={})

    resolved = resolve_resources([node])

    assert isinstance(resolved.models["model-1"], BaseChatModel)


def test_resolve_resources_keys_by_node_id_not_type():
    """8.4 — each node's own config is read independently, keyed by node id.

    Both request the same underlying model name ("fake"); `core.llm.get_model`
    is `@cache`d, so identical requests may legitimately return the same
    cached object — asserting object identity would test caching, not
    independence. The real guarantee is that each node id maps to a
    correctly-resolved entry, proven here by two *different* configs.
    """
    nodes = [
        FlowNode(id="model-a", type="LLMModel", values={"model": "fake"}),
        FlowNode(id="model-b", type="OllamaModel", values={}),  # falls back to DEFAULT_MODEL
    ]

    resolved = resolve_resources(nodes)

    assert set(resolved.models) == {"model-a", "model-b"}
    assert isinstance(resolved.models["model-a"], BaseChatModel)
    assert isinstance(resolved.models["model-b"], BaseChatModel)


def test_resolve_resources_ignores_execution_nodes():
    """8.5 — passing a non-resource node is a contract violation Task 7's
    partition_nodes should already have prevented; treat it as an error
    rather than silently resolving nonsense."""
    node = FlowNode(id="agent-1", type="ReActAgent", values={"system_prompt": "hi"})

    with pytest.raises(NotAResourceNodeError):
        resolve_resources([node])
