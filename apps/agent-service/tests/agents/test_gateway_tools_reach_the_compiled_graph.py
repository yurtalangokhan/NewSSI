"""Built-in tools-service tools must reach the compiled graph.

GraphBuilder.build()/build_async() dispatch through the strategy registry
(agents/graphs/strategies/*), not through GraphBuilder's own dead
_build_react/_build_zero_shot/etc. methods. gateway_tools was threaded onto
GraphBuilder and onto those dead methods, but never forwarded into
get_strategy(...) or read by any live strategy's build() — so every
DynamicAgent-backed graph silently dropped its built-in tools regardless of
schema type. This exercises the real build()/build_async() path for each
schema that binds tools directly to a model.
"""

from types import SimpleNamespace

import pytest

from agents.graphs.builder import GraphBuilder


def _fake_tool(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


def _patch_create_react_agent(monkeypatch, module_path: str) -> dict:
    captured: dict = {}

    def fake_create_react_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(f"{module_path}.create_react_agent", fake_create_react_agent)
    return captured


def _patch_create_agent(monkeypatch, module_path: str) -> dict:
    """The react strategy builds through langchain.agents.create_agent."""
    captured: dict = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(f"{module_path}.create_agent", fake_create_agent)
    return captured


@pytest.mark.asyncio
async def test_react_strategy_includes_gateway_tools(monkeypatch):
    captured = _patch_create_agent(monkeypatch, "agents.graphs.strategies.react")

    builder = GraphBuilder(model=object(), gateway_tools=[_fake_tool("builtin_search")])
    await builder.build_async("react", {"system_prompt": "Be helpful."})

    tool_names = {t.name for t in captured["tools"]}
    assert "builtin_search" in tool_names


@pytest.mark.asyncio
async def test_zero_shot_strategy_upgrades_to_react_and_includes_gateway_tools(monkeypatch):
    captured = _patch_create_agent(monkeypatch, "agents.graphs.strategies.react")

    builder = GraphBuilder(model=object(), gateway_tools=[_fake_tool("builtin_search")])
    await builder.build_async("zero_shot", {"system_prompt": "Be helpful."})

    tool_names = {t.name for t in captured["tools"]}
    assert "builtin_search" in tool_names


@pytest.mark.asyncio
async def test_plan_execute_strategy_includes_gateway_tools(monkeypatch):
    captured = _patch_create_react_agent(monkeypatch, "agents.graphs.strategies.plan_execute")

    builder = GraphBuilder(model=object(), gateway_tools=[_fake_tool("builtin_search")])
    await builder.build_async("plan_execute", {"system_prompt": "Be helpful."})

    tool_names = {t.name for t in captured["tools"]}
    assert "builtin_search" in tool_names


@pytest.mark.asyncio
async def test_supervisor_sub_agent_includes_gateway_tools(monkeypatch):
    # _build_sub_agent_graph imports create_react_agent locally (fetched
    # fresh from langgraph.prebuilt on each call), unlike the module-level
    # import the other strategies use — patch the source, not the module.
    captured = _patch_create_react_agent(monkeypatch, "langgraph.prebuilt")
    monkeypatch.setattr(
        "langgraph_supervisor.create_supervisor",
        lambda agents, **_kwargs: SimpleNamespace(
            compile=lambda **_kw: SimpleNamespace(name="compiled")
        ),
    )

    builder = GraphBuilder(model=object(), gateway_tools=[_fake_tool("builtin_search")])
    await builder.build_async(
        "supervisor",
        {
            "supervisor_prompt": "You are a team supervisor.",
            "sub_agents": [{"name": "worker", "system_prompt": "Do the work."}],
        },
    )

    tool_names = {t.name for t in captured["tools"]}
    assert "builtin_search" in tool_names


@pytest.mark.asyncio
async def test_pipeline_stage_includes_gateway_tools(monkeypatch):
    captured = _patch_create_react_agent(monkeypatch, "langgraph.prebuilt")
    monkeypatch.setattr(
        "langgraph_supervisor.create_supervisor",
        lambda agents, **_kwargs: SimpleNamespace(
            compile=lambda **_kw: SimpleNamespace(name="compiled")
        ),
    )

    builder = GraphBuilder(model=object(), gateway_tools=[_fake_tool("builtin_search")])
    await builder.build_async(
        "pipeline",
        {
            "pipeline_prompt": "Process sequentially.",
            "stages": [{"name": "stage-1", "system_prompt": "Do stage 1."}],
        },
    )

    tool_names = {t.name for t in captured["tools"]}
    assert "builtin_search" in tool_names
