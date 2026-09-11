"""Tests for Vector RAG compiler execution nodes.

Spec: .tmp/flow-canvas-design.md section 7.2.
Brief: .tmp/flow-canvas-task-32-brief.md
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage

from agents.graphs.flow_builder import FlowGraphBuilder
from models.flows import FlowSpec


@pytest.mark.asyncio
async def test_document_search_execution_node_calls_rag_service():
    """32.4 — DocumentSearch node searches rag-service and puts docs into scratch."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {
                    "id": "search-1",
                    "type": "DocumentSearch",
                    "values": {"collection": "col-uuid-123", "top_k": 3, "threshold": 0.75},
                },
                {"id": "out", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in",
                    "sourceHandle": "message",
                    "target": "search-1",
                    "targetHandle": "query",
                },
                {
                    "id": "e2",
                    "source": "search-1",
                    "sourceHandle": "documents",
                    "target": "out",
                    "targetHandle": "message",
                },
            ],
        }
    )

    mock_results = [
        {"content": "Chunk 1 content", "score": 0.85, "metadata": {"source": "doc1.pdf"}},
        {"content": "Chunk 2 content", "score": 0.78, "metadata": {"source": "doc2.pdf"}},
    ]

    with patch(
        "agents.graphs.flow_builder._execute_document_search", new_callable=AsyncMock
    ) as mock_search:
        mock_search.return_value = mock_results
        builder = FlowGraphBuilder()
        graph = await builder.build(spec)

        initial_state = {"messages": [HumanMessage(content="What is AI?")]}
        res = await graph.ainvoke(initial_state)

        assert "scratch" in res
        assert "search-1" in res["scratch"]
        assert res["scratch"]["search-1"] == mock_results


@pytest.mark.asyncio
async def test_document_context_formats_retrieved_documents():
    """32.5 — DocumentContext formats scratch documents into template."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {
                    "id": "ctx-1",
                    "type": "DocumentContext",
                    "values": {"template": "Context:\n{context}\n\nQuery: {query}"},
                },
                {"id": "out", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in",
                    "sourceHandle": "message",
                    "target": "ctx-1",
                    "targetHandle": "query",
                },
                {
                    "id": "e2",
                    "source": "ctx-1",
                    "sourceHandle": "context",
                    "target": "out",
                    "targetHandle": "message",
                },
            ],
        }
    )

    docs = [
        {"content": "LangGraph is a library.", "metadata": {"source": "guide.md"}},
        {"content": "Agents can use tools.", "metadata": {"source": "tools.md"}},
    ]

    builder = FlowGraphBuilder()
    graph = await builder.build(spec)

    initial_state = {
        "messages": [HumanMessage(content="Explain LangGraph")],
        "scratch": {"docs-input": docs},
    }
    res = await graph.ainvoke(initial_state)
    assert "scratch" in res
    assert "ctx-1" in res["scratch"]
    context_text = res["scratch"]["ctx-1"]
    assert "LangGraph is a library." in context_text
    assert "Explain LangGraph" in context_text
