"""Tests for Graph RAG compiler execution nodes.

Spec: .tmp/flow-canvas-design.md section 7.1.
Brief: .tmp/flow-canvas-task-33-brief.md
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage

from agents.graphs.flow_builder import FlowGraphBuilder
from models.flows import FlowSpec


@pytest.mark.asyncio
async def test_graph_search_execution_node():
    """33.5 — GraphSearch executes search against rag-service and puts results in scratch."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {
                    "id": "gs-1",
                    "type": "GraphSearch",
                    "values": {"collection": "gcol-1", "limit": 5},
                },
                {"id": "out", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in",
                    "sourceHandle": "message",
                    "target": "gs-1",
                    "targetHandle": "query",
                },
                {
                    "id": "e2",
                    "source": "gs-1",
                    "sourceHandle": "graph_data",
                    "target": "out",
                    "targetHandle": "message",
                },
            ],
        }
    )

    mock_data = [{"entity": "Alice", "relation": "WORKS_AT", "target": "Acme Corp"}]

    with patch(
        "agents.graphs.flow_builder._execute_graph_search", new_callable=AsyncMock
    ) as mock_exec:
        mock_exec.return_value = mock_data
        builder = FlowGraphBuilder()
        graph = await builder.build(spec)

        res = await graph.ainvoke({"messages": [HumanMessage(content="Where does Alice work?")]})
        assert "scratch" in res
        assert res["scratch"].get("gs-1") == mock_data


@pytest.mark.asyncio
async def test_graph_entity_search_execution_node():
    """33.6 — GraphEntitySearch searches entities and puts results in scratch."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {
                    "id": "ges-1",
                    "type": "GraphEntitySearch",
                    "values": {"collection": "gcol-1", "entity_type": "Person"},
                },
                {"id": "out", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in",
                    "sourceHandle": "message",
                    "target": "ges-1",
                    "targetHandle": "query",
                },
                {
                    "id": "e2",
                    "source": "ges-1",
                    "sourceHandle": "entities",
                    "target": "out",
                    "targetHandle": "message",
                },
            ],
        }
    )

    mock_entities = [{"id": "e-1", "name": "Alice", "type": "Person"}]

    with patch(
        "agents.graphs.flow_builder._execute_graph_entity_search", new_callable=AsyncMock
    ) as mock_exec:
        mock_exec.return_value = mock_entities
        builder = FlowGraphBuilder()
        graph = await builder.build(spec)

        res = await graph.ainvoke({"messages": [HumanMessage(content="Find Alice")]})
        assert "scratch" in res
        assert res["scratch"].get("ges-1") == mock_entities


@pytest.mark.asyncio
async def test_graph_neighborhood_execution_node():
    """33.7 — GraphNeighborhood traverses entity neighborhood into scratch."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {
                    "id": "gn-1",
                    "type": "GraphNeighborhood",
                    "values": {"collection": "gcol-1", "depth": 2},
                },
                {"id": "out", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in",
                    "sourceHandle": "message",
                    "target": "gn-1",
                    "targetHandle": "entity_id",
                },
                {
                    "id": "e2",
                    "source": "gn-1",
                    "sourceHandle": "subgraph",
                    "target": "out",
                    "targetHandle": "message",
                },
            ],
        }
    )

    mock_subgraph = {
        "nodes": [{"id": "alice"}, {"id": "acme"}],
        "edges": [{"source": "alice", "target": "acme"}],
    }

    with patch(
        "agents.graphs.flow_builder._execute_graph_neighborhood", new_callable=AsyncMock
    ) as mock_exec:
        mock_exec.return_value = mock_subgraph
        builder = FlowGraphBuilder()
        graph = await builder.build(spec)

        res = await graph.ainvoke({"messages": [HumanMessage(content="alice")]})
        assert "scratch" in res
        assert res["scratch"].get("gn-1") == mock_subgraph


@pytest.mark.asyncio
async def test_graph_stats_execution_node():
    """33.8 — GraphStats fetches graph metadata into scratch."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {"id": "gst-1", "type": "GraphStats", "values": {"collection": "gcol-1"}},
                {"id": "out", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in",
                    "sourceHandle": "message",
                    "target": "gst-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "gst-1",
                    "sourceHandle": "stats",
                    "target": "out",
                    "targetHandle": "message",
                },
            ],
        }
    )

    mock_stats = {"node_count": 150, "edge_count": 420, "density": 0.037}

    with patch(
        "agents.graphs.flow_builder._execute_graph_stats", new_callable=AsyncMock
    ) as mock_exec:
        mock_exec.return_value = mock_stats
        builder = FlowGraphBuilder()
        graph = await builder.build(spec)

        res = await graph.ainvoke({"messages": [HumanMessage(content="Get stats")]})
        assert "scratch" in res
        assert res["scratch"].get("gst-1") == mock_stats
