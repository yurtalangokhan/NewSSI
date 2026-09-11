"""Tests for FlowService — the orchestration layer over registry, validator,
migrations, and resolvers.

Persistence tests (6.13-6.15) use a fake repository, matching this project's
established DI pattern (Tasks 2/4/5) rather than a real database — the real
SQLAlchemy model/repository wiring is a thin, mechanical addition covered by
the migration itself, not by a dedicated unit test.

Spec: .tmp/flow-canvas-design.md section 4.6 (migration on save), 4.7 (validation).
Brief: .tmp/flow-canvas-task-6-brief.md
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.exceptions import UnknownComponentError
from domain.flows import resolvers as resolvers_module
from domain.flows.migrations import register_migration
from domain.flows.registry import ComponentRegistry
from domain.flows.resolvers import OptionItem, ResolverContext
from domain.flows.service import FLOW_UNKNOWN_RESOURCE, FlowService
from domain.flows.validator import (
    FLOW_RUNFLOW_CYCLE,
    FLOW_RUNFLOW_HITL,
    FLOW_RUNFLOW_UNPUBLISHED,
)
from models.flows import (
    ComponentHandles,
    ComponentKind,
    ComponentTemplate,
    FlowSpec,
    Handle,
    PortType,
)


def _template(type_name: str, template_version: int = 1) -> ComponentTemplate:
    return ComponentTemplate(
        type=type_name,
        category="test",
        display_name=type_name,
        template_version=template_version,
        kind=ComponentKind.EXECUTION,
        handles=ComponentHandles(outputs=[Handle(name="out", types=[PortType.MESSAGE])]),
    )


@pytest.fixture(autouse=True)
def _clear_resolver_cache():
    resolvers_module.clear_cache()
    yield
    resolvers_module.clear_cache()


def _valid_flow_dict() -> dict:
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "agent-1", "type": "ReActAgent", "values": {"system_prompt": "Be helpful."}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "agent-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "agent-1",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


# ---------------------------------------------------------------------------
# 6.1 — component listing
# ---------------------------------------------------------------------------


def test_list_components_returns_all_registered_grouped():
    service = FlowService()

    grouped = service.list_components()

    assert "core" in grouped
    assert any(t.type == "ChatInput" for t in grouped["core"])


# ---------------------------------------------------------------------------
# 6.2 — unknown component
# ---------------------------------------------------------------------------


def test_get_component_raises_for_unknown_type():
    service = FlowService()

    with pytest.raises(UnknownComponentError):
        service.get_component("NoSuchThing")


# ---------------------------------------------------------------------------
# 6.3 — structural validation (Task 3) surfaced through the service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_flow_returns_errors_and_warnings():
    service = FlowService()
    spec = FlowSpec.model_validate({"nodes": [{"id": "out-1", "type": "ChatOutput"}], "edges": []})

    result = await service.validate_flow(spec, ResolverContext(user_id="u1"))

    assert result.valid is False
    assert any(e.code == "FLOW_NO_ENTRY" for e in result.errors)


# ---------------------------------------------------------------------------
# 6.4 — resource-existence validation (Task 5), which the pure validator
# deliberately does not cover (it needs I/O)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_flow_reports_missing_resource_reference(monkeypatch):
    async def fake_llm_providers(context: ResolverContext) -> list[OptionItem]:
        return [OptionItem(value="real-provider", label="Real")]

    monkeypatch.setitem(resolvers_module._RESOLVERS, "llm.providers", fake_llm_providers)

    data = _valid_flow_dict()
    data["nodes"].append(
        {
            "id": "model-1",
            "type": "LLMModel",
            "values": {"provider": "ghost-provider", "model": "x"},
        }
    )
    spec = FlowSpec.model_validate(data)

    service = FlowService()
    result = await service.validate_flow(spec, ResolverContext(user_id="u1"))

    assert any(e.code == FLOW_UNKNOWN_RESOURCE and e.node_id == "model-1" for e in result.errors)


@pytest.mark.asyncio
async def test_validate_flow_checks_each_item_of_a_multiselect_reference(monkeypatch):
    """A MULTISELECT field (e.g. WebTools' `tools`) stores a list of ids, not
    one — checking the whole list against resolve_options as a single value
    always fails (str(["a", "b"]) is never a real option's value), flagging
    every multiselect tool reference as unknown even when every tool in it
    is real. Each item must be checked on its own."""

    async def fake_web_tools(context: ResolverContext) -> list[OptionItem]:
        return [
            OptionItem(value="fetch_web_page", label="Fetch Web Page"),
            OptionItem(value="search_web", label="Search Web"),
        ]

    monkeypatch.setitem(resolvers_module._RESOLVERS, "mcp.tools.web", fake_web_tools)

    data = _valid_flow_dict()
    data["nodes"].append(
        {
            "id": "WebTools-1",
            "type": "WebTools",
            "values": {"tools": ["fetch_web_page", "search_web"]},
        }
    )
    spec = FlowSpec.model_validate(data)

    service = FlowService()
    result = await service.validate_flow(spec, ResolverContext(user_id="u1"))

    assert not any(e.node_id == "WebTools-1" for e in result.errors)


@pytest.mark.asyncio
async def test_validate_flow_reports_the_specific_missing_item_in_a_multiselect(monkeypatch):
    async def fake_web_tools(context: ResolverContext) -> list[OptionItem]:
        return [OptionItem(value="fetch_web_page", label="Fetch Web Page")]

    monkeypatch.setitem(resolvers_module._RESOLVERS, "mcp.tools.web", fake_web_tools)

    data = _valid_flow_dict()
    data["nodes"].append(
        {
            "id": "WebTools-1",
            "type": "WebTools",
            "values": {"tools": ["fetch_web_page", "ghost_tool"]},
        }
    )
    spec = FlowSpec.model_validate(data)

    service = FlowService()
    result = await service.validate_flow(spec, ResolverContext(user_id="u1"))

    matching = [
        e for e in result.errors if e.code == FLOW_UNKNOWN_RESOURCE and e.node_id == "WebTools-1"
    ]
    assert len(matching) == 1
    assert "ghost_tool" in matching[0].message
    assert "fetch_web_page" not in matching[0].message


# ---------------------------------------------------------------------------
# 6.5 — migration wired on save (closes the design spec 4.6 loop)
# ---------------------------------------------------------------------------


def test_save_migrates_node_values_to_current_version():
    registry = ComponentRegistry()
    registry.register(_template("MigratableWidget", template_version=2))
    register_migration("MigratableWidget", 1, lambda v: {**v, "migrated": True})

    service = FlowService(registry=registry)
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {
                    "id": "n1",
                    "type": "MigratableWidget",
                    "template_version": 1,
                    "values": {"a": 1},
                }
            ],
            "edges": [],
        }
    )

    migrated = service.migrate_flow(spec)

    assert migrated.nodes[0].template_version == 2
    assert migrated.nodes[0].values == {"a": 1, "migrated": True}


# ---------------------------------------------------------------------------
# 6.13-6.15 — persistence, via a fake repository
# ---------------------------------------------------------------------------


class _FakeAgentDefRepo:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self._store: dict = {}

    async def create(self, **kwargs):
        obj = SimpleNamespace(id=uuid4(), **kwargs)
        self.created.append(kwargs)
        self._store[obj.id] = obj
        return obj

    async def update(self, definition_id, updates: dict):
        obj = self._store[definition_id]
        for key, value in updates.items():
            setattr(obj, key, value)
        return obj


@pytest.mark.asyncio
async def test_flow_spec_round_trips_through_repository():
    repo = _FakeAgentDefRepo()
    service = FlowService(repository=repo)
    spec = FlowSpec.model_validate(_valid_flow_dict())

    created = await service.save_flow(name="My Flow", flow_spec=spec)
    loaded = service.load_flow(created)

    assert loaded == spec


def test_definition_without_flow_spec_loads_as_none():
    service = FlowService()
    definition = SimpleNamespace(flow_spec=None)

    assert service.load_flow(definition) is None


@pytest.mark.asyncio
async def test_creating_definition_with_flow_spec_sets_graph_schema_to_flow():
    repo = _FakeAgentDefRepo()
    service = FlowService(repository=repo)
    spec = FlowSpec.model_validate(_valid_flow_dict())

    await service.save_flow(name="My Flow", flow_spec=spec)

    assert repo.created[0]["graph_schema"] == "flow"


# ---------------------------------------------------------------------------
# RunFlow reference checks (Phase 5) — the guards that need I/O
#
# The pure validator cannot do these: it would have to read *other* flows.
# validate_flow already mixes the pure result with I/O-backed checks and
# publish_flow calls it, so this is the existing seam, not a new one.
# ---------------------------------------------------------------------------

A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
C_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
D_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
H_ID = "88888888-8888-8888-8888-888888888888"


def _runs(*targets: str) -> dict:
    """A minimal spec whose only content is RunFlow nodes pointing somewhere."""
    return {
        "nodes": [
            {"id": f"rf-{i}", "type": "RunFlow", "values": {"flow_id": t}}
            for i, t in enumerate(targets)
        ],
        "edges": [],
    }


def _service_with_flows(published: dict[str, dict]) -> FlowService:
    """A FlowService whose definition repository knows these published flows."""

    class _Repo:
        async def get_by_id(self, definition_id):
            spec = published.get(str(definition_id))
            if spec is None:
                return None
            return SimpleNamespace(id=definition_id, name="x", graph_schema="flow", flow_spec=spec)

    return FlowService(repository=_Repo())


@pytest.mark.asyncio
async def test_a_flow_that_runs_itself_is_rejected():
    service = _service_with_flows({A_ID: _runs(A_ID)})
    issues = await service._check_flow_reference_cycle(
        FlowSpec.model_validate(_runs(A_ID)), definition_id=A_ID
    )
    assert any(i.code == FLOW_RUNFLOW_CYCLE for i in issues)


@pytest.mark.asyncio
async def test_an_indirect_cycle_is_rejected():
    """A -> B -> A. The reference graph is walked, not just the direct target."""
    service = _service_with_flows({B_ID: _runs(A_ID)})
    issues = await service._check_flow_reference_cycle(
        FlowSpec.model_validate(_runs(B_ID)), definition_id=A_ID
    )
    assert any(i.code == FLOW_RUNFLOW_CYCLE for i in issues)


@pytest.mark.asyncio
async def test_a_diamond_is_not_a_cycle():
    """A -> B, A -> C, B -> D, C -> D. Reaching the same flow by two routes is
    fine; only a path back to A is a cycle."""
    service = _service_with_flows(
        {
            B_ID: _runs(D_ID),
            C_ID: _runs(D_ID),
            D_ID: {"nodes": [], "edges": []},
        }
    )
    issues = await service._check_flow_reference_cycle(
        FlowSpec.model_validate(_runs(B_ID, C_ID)), definition_id=A_ID
    )
    assert issues == []


@pytest.mark.asyncio
async def test_a_cycle_among_other_flows_does_not_hang_the_walk():
    """B -> C -> B is someone else's problem, but the walk must terminate."""
    service = _service_with_flows({B_ID: _runs(C_ID), C_ID: _runs(B_ID)})
    issues = await service._check_flow_reference_cycle(
        FlowSpec.model_validate(_runs(B_ID)), definition_id=A_ID
    )
    assert issues == []


@pytest.mark.asyncio
async def test_an_unpublished_target_is_rejected():
    service = _service_with_flows({})
    issues = await service._check_run_flow_targets(FlowSpec.model_validate(_runs(A_ID)))
    assert any(i.code == FLOW_RUNFLOW_UNPUBLISHED for i in issues)
    assert issues[0].node_id == "rf-0"


@pytest.mark.asyncio
async def test_a_target_containing_human_input_is_rejected():
    """The child compiles with checkpointer=None, so an interrupt() inside it
    has nowhere to write and would vanish. Langflow refuses the same shape."""
    service = _service_with_flows(
        {
            H_ID: {
                "nodes": [
                    {
                        "id": "hi",
                        "type": "HumanInput",
                        "values": {"prompt": "?", "decisions": [{"label": "ok"}]},
                    }
                ],
                "edges": [],
            }
        }
    )
    issues = await service._check_run_flow_targets(FlowSpec.model_validate(_runs(H_ID)))
    assert any(i.code == FLOW_RUNFLOW_HITL for i in issues)


@pytest.mark.asyncio
async def test_a_published_target_without_human_input_is_clean():
    service = _service_with_flows({A_ID: {"nodes": [], "edges": []}})
    assert await service._check_run_flow_targets(FlowSpec.model_validate(_runs(A_ID))) == []
