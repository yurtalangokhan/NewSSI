"""A supervisor/pipeline sub-agent chain that loops back on itself must be
bounded, not recurse until the stack (or the event loop) gives out.

Two independent recursions needed a guard: builder.py's DB-loading step
(_load_sub_agents_from_db, walking sub_agent_ids) and the strategies'
in-memory nested-strategy construction (_build_sub_agent_graph, walking
inline "supervisor"/"pipeline" sub_agents/stages configs).
"""

import inspect
from types import SimpleNamespace
from uuid import uuid4

import pytest

from agents.graphs.builder import MAX_NESTED_SUB_AGENT_DEPTH, GraphBuilder


def _nested_supervisor_config(depth: int) -> dict:
    """A supervisor whose one sub-agent is itself a supervisor, `depth`
    levels deep, bottoming out in a plain react agent."""
    config: dict = {
        "name": "leaf",
        "graph_schema": "react",
        "system_prompt": "Be helpful.",
    }
    for level in range(depth):
        config = {
            "name": f"level-{level}",
            "graph_schema": "supervisor",
            "supervisor_prompt": "Coordinate.",
            "sub_agents": [config],
        }
    return config


def _patch_create_supervisor(monkeypatch) -> dict:
    captured: dict = {}

    def fake_create_supervisor(agents, **kwargs):
        captured["agents"] = agents
        return SimpleNamespace(compile=lambda **_kw: SimpleNamespace(name="compiled"))

    monkeypatch.setattr("langgraph_supervisor.create_supervisor", fake_create_supervisor)
    return captured


@pytest.mark.asyncio
async def test_in_memory_nested_supervisor_recursion_is_bounded(monkeypatch):
    _patch_create_supervisor(monkeypatch)
    monkeypatch.setattr("agents.graphs.strategies.react.create_agent", lambda **_kw: object())

    builder = GraphBuilder(model=object())
    deeply_nested = _nested_supervisor_config(MAX_NESTED_SUB_AGENT_DEPTH + 3)

    with pytest.raises(RecursionError):
        await builder.build_async("supervisor", deeply_nested)


@pytest.mark.asyncio
async def test_nested_supervisor_within_the_depth_limit_still_builds(monkeypatch):
    captured = _patch_create_supervisor(monkeypatch)
    monkeypatch.setattr("langgraph.prebuilt.create_react_agent", lambda **_kw: "leaf-agent")

    builder = GraphBuilder(model=object())
    shallow = _nested_supervisor_config(1)

    await builder.build_async("supervisor", shallow)

    # The nested supervisor's own build() result must be the real compiled
    # graph, not an un-awaited coroutine — build() is async, and the old
    # `return nested_strategy.build(agent_config)` (no await) handed the
    # coroutine object itself straight to create_supervisor().
    assert not any(inspect.iscoroutine(agent) for agent in captured["agents"])


class _CyclicRepository:
    """A sub-agent whose own sub_agent_ids points right back at itself."""

    def __init__(self, self_id):
        self.self_id = self_id

    async def get_by_id(self, agent_id):
        return SimpleNamespace(
            id=self.self_id,
            name="self-referencing",
            graph_schema="supervisor",
            system_prompt=None,
            model=None,
            mcp_tools=None,
            mcp_tool_configs=None,
            rag_config=None,
            supervisor_prompt=None,
            stages=None,
            pipeline_prompt=None,
            reflection_prompt=None,
            max_iterations=None,
            sub_agent_ids=[str(self.self_id)],
        )


@pytest.mark.asyncio
async def test_db_loaded_sub_agent_cycle_is_bounded(monkeypatch):
    self_id = uuid4()
    builder = GraphBuilder(model=object(), repository=_CyclicRepository(self_id))
    config = {"sub_agent_ids": [str(self_id)]}

    # Must return instead of recursing forever / raising RecursionError from
    # exhausting the Python call stack.
    await builder._load_sub_agents_from_db(config, target_field="sub_agents")

    assert len(config["sub_agents"]) <= MAX_NESTED_SUB_AGENT_DEPTH
