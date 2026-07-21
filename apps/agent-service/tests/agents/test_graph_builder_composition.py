"""Tests for GraphBuilder supervisor and pipeline composition."""

from agents.graphs.builder import GraphBuilder
from agents.graphs.schemas import GraphSchemaType


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


def test_supervisor_build_passes_sub_agent_graphs_to_supervisor(monkeypatch):
    """Supervisor should communicate with sub-agents through handoff graph nodes."""
    import langgraph_supervisor

    created = {}

    def fake_create_supervisor(agents, **kwargs):
        created["agents"] = agents
        created["kwargs"] = kwargs
        return FakeWorkflow(agents, kwargs["prompt"])

    monkeypatch.setattr(langgraph_supervisor, "create_supervisor", fake_create_supervisor)

    builder = GraphBuilder(model=object())
    built_sub_agents = []

    def fake_build_sub_agent_graph(config):
        marker = {"sub_agent_name": config["name"]}
        built_sub_agents.append(marker)
        return marker

    monkeypatch.setattr(builder, "_build_sub_agent_graph", fake_build_sub_agent_graph)

    graph = builder._build_supervisor(
        {
            "name": "root-supervisor",
            "supervisor_prompt": "Coordinate the team.",
            "sub_agents": [
                {"name": "researcher", "system_prompt": "Research facts."},
                {"name": "writer", "system_prompt": "Write clearly."},
            ],
        }
    )

    assert created["agents"] == built_sub_agents
    assert [agent["sub_agent_name"] for agent in created["agents"]] == [
        "researcher",
        "writer",
    ]
    assert "Available agents" in created["kwargs"]["prompt"]
    assert graph["compile_kwargs"]["name"] == "root-supervisor"


def test_pipeline_build_passes_stage_graphs_to_supervisor(monkeypatch):
    """Pipeline stages should be built as sub-agent graphs in configured order."""
    import langgraph_supervisor

    created = {}

    def fake_create_supervisor(agents, **kwargs):
        created["agents"] = agents
        created["kwargs"] = kwargs
        return FakeWorkflow(agents, kwargs["prompt"])

    monkeypatch.setattr(langgraph_supervisor, "create_supervisor", fake_create_supervisor)

    builder = GraphBuilder(model=object())

    def fake_build_sub_agent_graph(config):
        return {"stage_name": config["name"]}

    monkeypatch.setattr(builder, "_build_sub_agent_graph", fake_build_sub_agent_graph)

    graph = builder._build_pipeline(
        {
            "name": "document-pipeline",
            "pipeline_prompt": "Process sequentially.",
            "stages": [
                {"name": "intake", "system_prompt": "Read input."},
                {"name": "verify", "system_prompt": "Check output."},
            ],
        }
    )

    assert [agent["stage_name"] for agent in created["agents"]] == ["intake", "verify"]
    assert "intake" in created["kwargs"]["prompt"]
    assert "verify" in created["kwargs"]["prompt"]
    assert graph["compile_kwargs"]["name"] == "document-pipeline"


def test_nested_supervisor_sub_agent_is_preserved_as_nested_graph(monkeypatch):
    """A supervisor selected as a sub-agent should not be flattened into ReAct."""
    calls = {}

    def fake_build(self, schema_type, config):
        calls["schema_type"] = schema_type
        calls["config"] = config
        return {"nested_schema": schema_type}

    monkeypatch.setattr(GraphBuilder, "build", fake_build)

    builder = GraphBuilder(model=object())
    graph = builder._build_sub_agent_graph(
        {
            "name": "nested-team",
            "graph_schema": "supervisor",
            "supervisor_prompt": "Coordinate nested team.",
            "sub_agents": [{"name": "leaf", "system_prompt": "Do work."}],
        }
    )

    assert graph == {"nested_schema": GraphSchemaType.SUPERVISOR}
    assert calls["schema_type"] == GraphSchemaType.SUPERVISOR
    assert calls["config"]["name"] == "nested-team"
