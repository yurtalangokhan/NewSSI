"""Supervisor and pipeline composition, through the build path used in production.

These used to drive GraphBuilder._build_supervisor/_build_pipeline/
_build_sub_agent_graph directly. Nothing dispatched to those: build() and
build_async() go through the strategy registry, so the composition rules
below were only ever asserted against methods no request reached.
"""

import pytest

from agents.graphs.builder import GraphBuilder
from schemas.agent_graphs import GraphSchemaType


class FakeWorkflow:
    """Small stand-in for langgraph-supervisor workflow."""

    def __init__(self, agents, prompt):
        self.agents = agents
        self.prompt = prompt

    def compile(self, **kwargs):
        return {
            "agents": self.agents,
            "prompt": self.prompt,
            "compile_kwargs": kwargs,
        }


def _capture_supervisor(monkeypatch) -> dict:
    import langgraph_supervisor

    created: dict = {}

    def fake_create_supervisor(agents, **kwargs):
        created["agents"] = agents
        created["kwargs"] = kwargs
        return FakeWorkflow(agents, kwargs["prompt"])

    monkeypatch.setattr(langgraph_supervisor, "create_supervisor", fake_create_supervisor)
    return created


def _capture_sub_agents(monkeypatch, strategy_module: str, key: str) -> list[dict]:
    """Stand in for the sub-agent graph each strategy builds per entry."""
    built: list[dict] = []

    async def fake_build_sub_agent_graph(_self, config):
        marker = {key: config["name"]}
        built.append(marker)
        return marker

    monkeypatch.setattr(
        f"{strategy_module}._build_sub_agent_graph",
        fake_build_sub_agent_graph,
    )
    return built


@pytest.mark.asyncio
async def test_supervisor_build_passes_sub_agent_graphs_to_supervisor(monkeypatch):
    """Supervisor should communicate with sub-agents through handoff graph nodes."""
    created = _capture_supervisor(monkeypatch)
    built_sub_agents = _capture_sub_agents(
        monkeypatch,
        "agents.graphs.strategies.supervisor.SupervisorGraphStrategy",
        "sub_agent_name",
    )

    graph = await GraphBuilder(model=object()).build_async(
        "supervisor",
        {
            "name": "root-supervisor",
            "supervisor_prompt": "Coordinate the team.",
            "sub_agents": [
                {"name": "researcher", "system_prompt": "Research facts."},
                {"name": "writer", "system_prompt": "Write clearly."},
            ],
        },
    )

    assert created["agents"] == built_sub_agents
    assert [agent["sub_agent_name"] for agent in created["agents"]] == [
        "researcher",
        "writer",
    ]
    assert "Available agents" in created["kwargs"]["prompt"]
    assert graph["compile_kwargs"]["name"] == "root-supervisor"


@pytest.mark.asyncio
async def test_pipeline_build_passes_stage_graphs_to_supervisor(monkeypatch):
    """Pipeline stages should be built as sub-agent graphs in configured order."""
    created = _capture_supervisor(monkeypatch)
    _capture_sub_agents(
        monkeypatch,
        "agents.graphs.strategies.pipeline.PipelineGraphStrategy",
        "stage_name",
    )

    graph = await GraphBuilder(model=object()).build_async(
        "pipeline",
        {
            "name": "document-pipeline",
            "pipeline_prompt": "Process sequentially.",
            "stages": [
                {"name": "intake", "system_prompt": "Read input."},
                {"name": "verify", "system_prompt": "Check output."},
            ],
        },
    )

    assert [agent["stage_name"] for agent in created["agents"]] == ["intake", "verify"]
    assert "intake" in created["kwargs"]["prompt"]
    assert "verify" in created["kwargs"]["prompt"]
    assert graph["compile_kwargs"]["name"] == "document-pipeline"


@pytest.mark.asyncio
async def test_nested_supervisor_sub_agent_is_preserved_as_nested_graph(monkeypatch):
    """A supervisor selected as a sub-agent should not be flattened into ReAct.

    The nested level is built by constructing the matching strategy again,
    one depth deeper -- not by falling through to the ReAct branch below it.
    """
    from agents.graphs.strategies.supervisor import SupervisorGraphStrategy

    calls: dict = {}

    async def fake_build(self, config):
        calls["strategy"] = type(self)
        calls["config"] = config
        calls["depth"] = self._depth
        return {"nested_schema": self.schema_type}

    monkeypatch.setattr(SupervisorGraphStrategy, "build", fake_build)

    strategy = SupervisorGraphStrategy(model=object())
    graph = await strategy._build_sub_agent_graph(
        {
            "name": "nested-team",
            "graph_schema": "supervisor",
            "supervisor_prompt": "Coordinate nested team.",
            "sub_agents": [{"name": "leaf", "system_prompt": "Do work."}],
        }
    )

    assert graph == {"nested_schema": GraphSchemaType.SUPERVISOR}
    assert calls["strategy"] is SupervisorGraphStrategy
    assert calls["config"]["name"] == "nested-team"
    assert calls["depth"] == 1, "the nested level must count toward the recursion guard"
