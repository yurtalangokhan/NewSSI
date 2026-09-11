"""Tests for domain/flows/agent_expansion.py — agent-to-flow materialization.

Per-unit tests call each pure/async function directly with an injected fake
repository/service, mirroring tests/domain/flows/test_resolvers.py's pattern:
the real categorization/materialization logic runs for real, only the
DB/service boundary is faked.

Spec: .tmp/2026-08-27-agent-flow-expansion-design.md
Plan: .tmp/2026-08-27-agent-flow-expansion-plan.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from domain.flows import agent_expansion


class _FakeMCPToolService:
    def __init__(self, categories: dict[str, list[dict]]):
        self._categories = categories

    async def list_categories(self) -> list[str]:
        return list(self._categories)

    async def get_tools_by_category(self, category: str) -> list[dict]:
        return self._categories.get(category, [])


class _FailingMCPToolService:
    async def list_categories(self):
        raise RuntimeError("service unreachable")


@pytest.mark.asyncio
async def test_groups_tools_by_category_using_the_live_service():
    service = _FakeMCPToolService(
        {
            "file": [{"name": "read_file"}, {"name": "write_file"}],
            "git": [{"name": "git_status"}],
        }
    )

    result = await agent_expansion.resolve_tool_categories(
        ["read_file", "git_status"], service=service
    )

    assert result == {"file": ["read_file"], "git": ["git_status"]}


@pytest.mark.asyncio
async def test_falls_back_to_builtin_categories_when_service_unavailable():
    result = await agent_expansion.resolve_tool_categories(
        ["web_search"], service=_FailingMCPToolService()
    )

    assert result == {"web": ["web_search"]}


@pytest.mark.asyncio
async def test_ignores_tool_names_with_no_known_category():
    service = _FakeMCPToolService({"file": [{"name": "read_file"}]})

    result = await agent_expansion.resolve_tool_categories(
        ["read_file", "totally_unknown_tool"], service=service
    )

    assert result == {"file": ["read_file"]}


@pytest.mark.asyncio
async def test_empty_tool_list_returns_empty_dict():
    result = await agent_expansion.resolve_tool_categories([], service=_FakeMCPToolService({}))

    assert result == {}


class _FakeDefinition:
    def __init__(
        self,
        *,
        graph_schema: str = "react",
        system_prompt: str | None = "Be helpful.",
        model: str | None = "gpt-4o",
        memory_type: str | None = "none",
    ):
        self.graph_schema = graph_schema
        self.system_prompt = system_prompt
        self.model = model
        self.memory_type = memory_type


def test_select_agent_node_type_react_maps_to_react_agent():
    assert agent_expansion.select_agent_node_type("react", has_tools=True) == "ReActAgent"
    assert agent_expansion.select_agent_node_type("react", has_tools=False) == "ReActAgent"


def test_select_agent_node_type_zero_shot_promotes_to_react_when_tools_present():
    assert agent_expansion.select_agent_node_type("zero_shot", has_tools=True) == "ReActAgent"
    assert agent_expansion.select_agent_node_type("zero_shot", has_tools=False) == "ZeroShotAgent"


def test_select_agent_node_type_covers_plan_execute_and_self_reflect():
    assert (
        agent_expansion.select_agent_node_type("plan_execute", has_tools=False)
        == "PlanExecuteAgent"
    )
    assert (
        agent_expansion.select_agent_node_type("self_reflect", has_tools=False)
        == "SelfReflectAgent"
    )


def test_materialize_single_brain_builds_agent_input_and_model_nodes():
    definition = _FakeDefinition(graph_schema="react", model="gpt-4o", memory_type="none")

    nodes, edges = agent_expansion.materialize_single_brain(definition, {})

    by_type = {n.type: n for n in nodes}
    assert "ReActAgent" in by_type
    assert by_type["ReActAgent"].values["system_prompt"] == "Be helpful."
    assert "ChatInput" in by_type
    assert by_type["LLMModel"].values["model"] == "gpt-4o"

    agent_id = by_type["ReActAgent"].id
    chat_input_id = by_type["ChatInput"].id
    model_id = by_type["LLMModel"].id

    edge_pairs = {(e.source, e.source_handle, e.target, e.target_handle) for e in edges}
    assert (chat_input_id, "message", agent_id, "input") in edge_pairs
    assert (model_id, "model", agent_id, "model") in edge_pairs


def test_materialize_single_brain_wires_one_node_per_tool_category():
    definition = _FakeDefinition(graph_schema="react")
    tool_categories = {"file": ["read_file"], "git": ["git_status"]}

    nodes, edges = agent_expansion.materialize_single_brain(definition, tool_categories)

    by_type = {n.type: n for n in nodes}
    assert by_type["FileTools"].values["tools"] == ["read_file"]
    assert by_type["GitTools"].values["tools"] == ["git_status"]

    agent_id = by_type["ReActAgent"].id
    tools_edges = {
        e.target_handle
        for e in edges
        if e.target == agent_id and e.source in (by_type["FileTools"].id, by_type["GitTools"].id)
    }
    assert tools_edges == {"tools"}


def test_materialize_single_brain_omits_memory_node_when_disabled():
    definition = _FakeDefinition(memory_type="none")

    nodes, _edges = agent_expansion.materialize_single_brain(definition, {})

    assert "LongTermMemory" not in {n.type for n in nodes}


def test_materialize_single_brain_adds_memory_node_when_long_term_enabled():
    definition = _FakeDefinition(memory_type="long_term")

    nodes, edges = agent_expansion.materialize_single_brain(definition, {})

    by_type = {n.type: n for n in nodes}
    assert "LongTermMemory" in by_type
    agent_id = by_type["ReActAgent"].id
    assert (by_type["LongTermMemory"].id, "memory", agent_id, "memory") in {
        (e.source, e.source_handle, e.target, e.target_handle) for e in edges
    }


def test_materialize_single_brain_node_ids_are_unique_and_edges_resolve():
    definition = _FakeDefinition(memory_type="long_term")
    nodes, edges = agent_expansion.materialize_single_brain(definition, {"file": ["read_file"]})

    node_ids = {n.id for n in nodes}
    assert len(node_ids) == len(nodes)
    for edge in edges:
        assert edge.source in node_ids
        assert edge.target in node_ids


class _FakeStageDefinition:
    def __init__(self, *, name: str, system_prompt: str, model: str | None, mcp_tools: list[str]):
        self.name = name
        self.system_prompt = system_prompt
        self.model = model
        self.mcp_tools = mcp_tools


class _FakeRepoForStages:
    def __init__(self, by_id: dict[str, _FakeStageDefinition]):
        self._by_id = by_id

    async def get_by_id(self, definition_id):
        return self._by_id.get(str(definition_id))


class _FakePipelineDefinition:
    def __init__(self, *, sub_agent_ids: list[str], stages: list[dict]):
        self.sub_agent_ids = sub_agent_ids
        self.stages = stages


@pytest.mark.asyncio
async def test_resolve_pipeline_stage_configs_orders_resolved_ids_before_inline_stages():
    stage_id = str(uuid4())
    repo = _FakeRepoForStages(
        {
            stage_id: _FakeStageDefinition(
                name="Research",
                system_prompt="Research it.",
                model="gpt-4o",
                mcp_tools=["web_search"],
            )
        }
    )
    definition = _FakePipelineDefinition(
        sub_agent_ids=[stage_id],
        stages=[
            {
                "name": "Summarize",
                "system_prompt": "Summarize it.",
                "model": "gpt-4o-mini",
                "mcp_tools": [],
            }
        ],
    )

    stages = await agent_expansion.resolve_pipeline_stage_configs(definition, repo)

    assert [s["name"] for s in stages] == ["Research", "Summarize"]
    assert stages[0]["mcp_tools"] == ["web_search"]


@pytest.mark.asyncio
async def test_resolve_pipeline_stage_configs_skips_unresolvable_ids():
    repo = _FakeRepoForStages({})
    definition = _FakePipelineDefinition(sub_agent_ids=[str(uuid4())], stages=[])

    stages = await agent_expansion.resolve_pipeline_stage_configs(definition, repo)

    assert stages == []


@pytest.mark.asyncio
async def test_resolve_pipeline_stage_configs_handles_no_sub_agent_ids():
    definition = _FakePipelineDefinition(
        sub_agent_ids=[],
        stages=[{"name": "Only stage", "system_prompt": "Go.", "model": None, "mcp_tools": []}],
    )

    stages = await agent_expansion.resolve_pipeline_stage_configs(
        definition, _FakeRepoForStages({})
    )

    assert [s["name"] for s in stages] == ["Only stage"]


def test_materialize_pipeline_chains_stages_with_message_edges():
    stage_configs = [
        {
            "name": "Research",
            "system_prompt": "Research.",
            "model": "gpt-4o",
            "mcp_tools": ["web_search"],
        },
        {
            "name": "Summarize",
            "system_prompt": "Summarize.",
            "model": "gpt-4o-mini",
            "mcp_tools": [],
        },
    ]
    tool_categories_by_stage = [{"web": ["web_search"]}, {}]

    nodes, edges = agent_expansion.materialize_pipeline(stage_configs, tool_categories_by_stage)

    stage_nodes = [n for n in nodes if n.type == "PipelineStage"]
    assert len(stage_nodes) == 2
    assert stage_nodes[0].values["name"] == "Research"
    assert stage_nodes[1].values["name"] == "Summarize"

    chain_edge = next(
        e for e in edges if e.source == stage_nodes[0].id and e.target == stage_nodes[1].id
    )
    assert chain_edge.source_handle == "output"
    assert chain_edge.target_handle == "input"


def test_materialize_pipeline_offsets_each_stage_so_clusters_do_not_overlap():
    stage_configs = [
        {"name": "A", "system_prompt": "a", "model": "gpt-4o", "mcp_tools": ["read_file"]},
        {"name": "B", "system_prompt": "b", "model": "gpt-4o", "mcp_tools": ["read_file"]},
        {"name": "C", "system_prompt": "c", "model": "gpt-4o", "mcp_tools": ["read_file"]},
    ]
    tool_categories_by_stage = [
        {"file": ["read_file"]},
        {"file": ["read_file"]},
        {"file": ["read_file"]},
    ]

    nodes, _edges = agent_expansion.materialize_pipeline(stage_configs, tool_categories_by_stage)

    stage_nodes = [n for n in nodes if n.type == "PipelineStage"]
    xs = [n.position.x for n in stage_nodes]
    # Each successive stage sits clearly to the right of the previous one, by
    # more than the intra-cluster spread (resource nodes sit +320 from their
    # stage), so no two stages' node clusters land on top of each other.
    assert xs[1] - xs[0] > 320
    assert xs[2] - xs[1] > 320


def test_materialize_pipeline_only_first_stage_gets_a_chat_input():
    stage_configs = [
        {"name": "A", "system_prompt": "a", "model": None, "mcp_tools": []},
        {"name": "B", "system_prompt": "b", "model": None, "mcp_tools": []},
    ]

    nodes, _edges = agent_expansion.materialize_pipeline(stage_configs, [{}, {}])

    assert len([n for n in nodes if n.type == "ChatInput"]) == 1


def test_materialize_pipeline_each_stage_gets_its_own_model_and_tool_nodes():
    stage_configs = [
        {"name": "A", "system_prompt": "a", "model": "gpt-4o", "mcp_tools": ["read_file"]},
    ]

    nodes, _edges = agent_expansion.materialize_pipeline(stage_configs, [{"file": ["read_file"]}])

    assert "LLMModel" in {n.type for n in nodes}
    assert "FileTools" in {n.type for n in nodes}


def test_materialize_pipeline_single_stage_has_no_chain_edge():
    nodes, edges = agent_expansion.materialize_pipeline(
        [{"name": "Only", "system_prompt": "x", "model": None, "mcp_tools": []}], [{}]
    )

    stage_nodes = [n for n in nodes if n.type == "PipelineStage"]
    stage_to_stage_edges = [
        e
        for e in edges
        if e.source in {n.id for n in stage_nodes} and e.target in {n.id for n in stage_nodes}
    ]
    assert stage_to_stage_edges == []


@dataclass
class _FakeCloneableDefinition:
    id: str
    name: str
    persona_id: int | None
    agent_type: str = "dynamic"
    description: str | None = None
    graph_schema: str = "react"
    brain_type: str = "llm"
    memory_type: str = "none"
    system_prompt: str | None = "hi"
    model: str | None = "gpt-4o"
    mcp_tools: list = field(default_factory=list)
    mcp_tool_configs: dict = field(default_factory=dict)
    rag_config: dict = field(default_factory=dict)
    sub_agents: list = field(default_factory=list)
    sub_agent_ids: list = field(default_factory=list)
    supervisor_prompt: str | None = None
    stages: list = field(default_factory=list)
    pipeline_prompt: str | None = None
    reflection_prompt: str | None = None
    max_iterations: int = 3
    tags: list = field(default_factory=list)
    version: str = "1.0.0"


class _FakeCloneRepo:
    def __init__(self, rows: dict[str, _FakeCloneableDefinition]):
        self._rows = dict(rows)
        self.created: list[dict] = []

    async def get_by_id(self, definition_id):
        return self._rows.get(str(definition_id))

    async def create(self, **kwargs) -> _FakeCloneableDefinition:
        self.created.append(kwargs)
        new_id = f"clone-{len(self.created)}"
        row = _FakeCloneableDefinition(id=new_id, **kwargs)
        self._rows[new_id] = row
        return row


class _FakeDepthService:
    def __init__(self, depth_by_id: dict[str, int]):
        self._depth_by_id = depth_by_id

    async def get_composition_depth_async(self, agent_id):
        return self._depth_by_id.get(str(agent_id), 0)


@pytest.mark.asyncio
async def test_clone_sub_agent_tree_creates_a_new_row_per_top_level_id():
    child = _FakeCloneableDefinition(id="child-1", name="Child", persona_id=7)
    repo = _FakeCloneRepo({"child-1": child})

    new_ids = await agent_expansion.clone_sub_agent_tree(
        ["child-1"], repo, depth_service=_FakeDepthService({})
    )

    assert len(new_ids) == 1
    assert new_ids[0] != "child-1"
    assert len(repo.created) == 1


@pytest.mark.asyncio
async def test_clone_sub_agent_tree_clones_never_reuse_the_source_name_or_persona():
    child = _FakeCloneableDefinition(id="child-1", name="Support Bot", persona_id=7)
    repo = _FakeCloneRepo({"child-1": child})

    await agent_expansion.clone_sub_agent_tree(
        ["child-1"], repo, depth_service=_FakeDepthService({})
    )

    created = repo.created[0]
    assert created["name"] != "Support Bot"
    assert created["name"].startswith("Support Bot")
    assert created["persona_id"] is None


@pytest.mark.asyncio
async def test_clone_sub_agent_tree_recurses_into_nested_sub_agent_ids():
    grandchild = _FakeCloneableDefinition(id="gc-1", name="Grandchild", persona_id=None)
    child = _FakeCloneableDefinition(
        id="child-1", name="Child", persona_id=None, sub_agent_ids=["gc-1"]
    )
    repo = _FakeCloneRepo({"child-1": child, "gc-1": grandchild})

    await agent_expansion.clone_sub_agent_tree(
        ["child-1"], repo, depth_service=_FakeDepthService({})
    )

    assert len(repo.created) == 2  # grandchild clone + child clone
    child_creation = next(c for c in repo.created if c["name"].startswith("Child"))
    # the child clone's sub_agent_ids must point at the NEW grandchild clone id,
    # never the original "gc-1"
    assert child_creation["sub_agent_ids"] == [
        next(
            c_id
            for c_id, row in repo._rows.items()
            if row.name.startswith("Grandchild") and c_id != "gc-1"
        )
    ]


@pytest.mark.asyncio
async def test_clone_sub_agent_tree_raises_before_writing_anything_past_max_depth():
    from domain.flows.agent_expansion import AgentExpansionError
    from service.CompositionValidationService import CompositionValidationService

    child = _FakeCloneableDefinition(id="child-1", name="Child", persona_id=None)
    repo = _FakeCloneRepo({"child-1": child})
    depth_service = _FakeDepthService({"child-1": CompositionValidationService.MAX_DEPTH})

    with pytest.raises(AgentExpansionError):
        await agent_expansion.clone_sub_agent_tree(["child-1"], repo, depth_service=depth_service)

    assert repo.created == []


@pytest.mark.asyncio
async def test_expand_agent_definition_dispatches_single_brain_to_materialize_single_brain():
    definition = _FakeDefinition(graph_schema="react", model="gpt-4o", memory_type="none")

    class _Repo:
        async def get_by_id(self, _id):
            return definition

    nodes, _edges = await agent_expansion.expand_agent_definition(
        "any-id", _Repo(), mcp_service=_FakeMCPToolService({})
    )

    assert any(n.type == "ReActAgent" for n in nodes)


@pytest.mark.asyncio
async def test_expand_agent_definition_dispatches_pipeline_to_materialize_pipeline():
    definition = _FakePipelineDefinition(
        sub_agent_ids=[],
        stages=[{"name": "Only", "system_prompt": "x", "model": None, "mcp_tools": []}],
    )
    definition.graph_schema = "pipeline"

    class _Repo:
        async def get_by_id(self, _id):
            return definition

    nodes, _edges = await agent_expansion.expand_agent_definition(
        "any-id", _Repo(), mcp_service=_FakeMCPToolService({})
    )

    assert any(n.type == "PipelineStage" for n in nodes)


@pytest.mark.asyncio
async def test_expand_agent_definition_dispatches_supervisor_to_a_single_node_plus_clones():
    child = _FakeCloneableDefinition(id="child-1", name="Child", persona_id=None)

    @dataclass
    class _SupervisorDefinition:
        graph_schema: str = "supervisor"
        supervisor_prompt: str = "Supervise."
        sub_agent_ids: list = field(default_factory=lambda: ["child-1"])

    class _Repo:
        def __init__(self):
            self._rows = {"child-1": child}
            self.created = []

        async def get_by_id(self, definition_id):
            if str(definition_id) == "top":
                return _SupervisorDefinition()
            return self._rows.get(str(definition_id))

        async def create(self, **kwargs):
            new_id = f"clone-{len(self.created)}"
            self.created.append(kwargs)
            row = _FakeCloneableDefinition(id=new_id, **kwargs)
            self._rows[new_id] = row
            return row

    nodes, edges = await agent_expansion.expand_agent_definition(
        "top", _Repo(), depth_service=_FakeDepthService({})
    )

    assert len(nodes) == 1
    assert nodes[0].type == "Supervisor"
    assert nodes[0].values["supervisor_prompt"] == "Supervise."
    assert nodes[0].values["sub_agents"] == ["clone-0"]
    assert edges == []


@pytest.mark.asyncio
async def test_expand_agent_definition_rejects_flow_backed_agents():
    from domain.flows.agent_expansion import AgentExpansionError

    @dataclass
    class _FlowDefinition:
        graph_schema: str = "flow"

    class _Repo:
        async def get_by_id(self, _id):
            return _FlowDefinition()

    with pytest.raises(AgentExpansionError):
        await agent_expansion.expand_agent_definition("any-id", _Repo())


@pytest.mark.asyncio
async def test_expand_agent_definition_raises_for_unknown_id():
    from domain.flows.agent_expansion import AgentExpansionError

    class _Repo:
        async def get_by_id(self, _id):
            return None

    with pytest.raises(AgentExpansionError):
        await agent_expansion.expand_agent_definition("missing", _Repo())
