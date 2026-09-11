"""Tests for datasource execution & resource nodes in flow_builder (P8 Task 47).

Spec: .tmp/flow-canvas-design.md section 7.6.
Brief: .tmp/flow-canvas-task-47-brief.md
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.graphs.flow_builder import (
    FlowGraphBuilder,
    FlowNode,
    ResolvedResources,
    make_node,
    resolve_resources,
)
from domain.flows.registry import get_registry
from models.flows import FlowEdge, FlowSpec


def test_resolve_resources_accepts_airbyte_datasource():
    """47.4 — resolve_resources accepts AirbyteDatasource without error."""
    nodes = [FlowNode(id="ds_1", type="AirbyteDatasource", values={"datasource_id": "ds-123"})]
    resolved = resolve_resources(nodes)
    assert resolved.datasource_ids.get("ds_1") == "ds-123"


def test_resolved_resources_carries_datasource_ids_by_node_id():
    """47.5 — ResolvedResources carries datasource_ids mapping."""
    res = ResolvedResources(datasource_ids={"ds_node": "coll_456"})
    assert res.datasource_ids["ds_node"] == "coll_456"


@pytest.mark.asyncio
async def test_sync_trigger_calls_data_controller_trigger_sync():
    """47.8 — SyncTrigger node calls DataController.trigger_sync with datasource_id."""
    node = FlowNode(
        id="st_1",
        type="SyncTrigger",
        values={"datasource_id": "ds-999"},
    )
    resources = ResolvedResources()
    runnable = await make_node(node, resources)

    mock_ctrl = MagicMock()
    mock_ctrl.trigger_sync = AsyncMock(return_value={"status": "Sync started", "id": "ds-999"})

    with patch("controller.get_data_controller", return_value=mock_ctrl):
        state = {"scratch": {}}
        res = await runnable(state, {})

    mock_ctrl.trigger_sync.assert_awaited_once_with("ds-999", triggered_by="flow")
    assert res["scratch"]["st_1"] == {"status": "Sync started", "id": "ds-999"}


@pytest.mark.asyncio
async def test_sync_trigger_in_flight_sync_returns_already_queued_not_an_error():
    """47.9 — Concurrent/in-flight sync returns status dict cleanly without raising."""
    node = FlowNode(
        id="st_1",
        type="SyncTrigger",
        values={"datasource_id": "ds-999"},
    )
    resources = ResolvedResources()
    runnable = await make_node(node, resources)

    mock_ctrl = MagicMock()
    mock_ctrl.trigger_sync = AsyncMock(
        return_value={"status": "Already syncing or queued", "id": "ds-999"}
    )

    with patch("controller.get_data_controller", return_value=mock_ctrl):
        state = {"scratch": {}}
        res = await runnable(state, {})

    assert res["scratch"]["st_1"]["status"] == "Already syncing or queued"


@pytest.mark.asyncio
async def test_sync_trigger_reachable_via_router_branch_compiles():
    """47.7 — Flow with Router routing to SyncTrigger compiles into LangGraph."""
    spec = FlowSpec(
        nodes=[
            FlowNode(id="in", type="ChatInput", values={}),
            FlowNode(id="router", type="Router", values={"routes": ["sync_branch", "default"]}),
            FlowNode(id="st", type="SyncTrigger", values={"datasource_id": "ds-1"}),
            FlowNode(id="out", type="ChatOutput", values={}),
        ],
        edges=[
            FlowEdge(
                id="e1", source="in", source_handle="output", target="router", target_handle="input"
            ),
            FlowEdge(
                id="e2",
                source="router",
                source_handle="sync_branch",
                target="st",
                target_handle="trigger",
            ),
            FlowEdge(
                id="e3", source="st", source_handle="result", target="out", target_handle="input"
            ),
        ],
    )
    builder = FlowGraphBuilder(registry=get_registry())
    graph = await builder.build(spec)
    assert graph is not None
