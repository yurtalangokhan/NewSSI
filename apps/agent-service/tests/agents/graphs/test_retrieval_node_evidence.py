"""Flow retrieval nodes report what they retrieved as a knowledge evidence card."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from schemas.knowledge_evidence import EvidenceKind
from langchain_core.messages import HumanMessage

from agents.graphs.flow import FlowGraphBuilder
from integrations.rag_client import RagChunk
from schemas.flows import FlowSpec

_RETRIEVAL = "agents.graphs.flow.nodes.retrieval"


def _spec(node_type: str, values: dict, output_handle: str) -> FlowSpec:
    return FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {"id": "search-1", "type": node_type, "values": values},
                {"id": "out", "type": "ChatOutput"},
            ],
            "edges": [
                {"id": "e1", "source": "in", "sourceHandle": "message", "target": "search-1", "targetHandle": "query"},
                {
                    "id": "e2",
                    "source": "search-1",
                    "sourceHandle": output_handle,
                    "target": "out",
                    "targetHandle": "message",
                },
            ],
        }
    )


async def _run(spec: FlowSpec, *, reported: bool):
    report_evidence = AsyncMock(return_value=reported)
    with (
        patch(f"{_RETRIEVAL}.report_stage_evidence", report_evidence),
        patch(f"{_RETRIEVAL}.report_stage_output") as report_output,
    ):
        graph = await FlowGraphBuilder().build(spec)
        result = await graph.ainvoke({"messages": [HumanMessage(content="yıllık izin devri")]})
    return result, report_evidence, report_output


@pytest.mark.asyncio
async def test_document_search_reports_its_chunks_as_evidence():
    chunks = [RagChunk(text="Unused leave carries over.", score=0.9, metadata={"source": "a.pdf"}, id="c1")]
    with patch(f"{_RETRIEVAL}._execute_document_search", AsyncMock(return_value=chunks)):
        result, report_evidence, report_output = await _run(
            _spec("DocumentSearch", {"collection": "col-1", "top_k": 3}, "documents"), reported=True
        )

    node_id, evidence = report_evidence.await_args.args
    assert node_id == "search-1"
    assert evidence.kind is EvidenceKind.DOCUMENT
    assert evidence.tool == "document_search"
    assert evidence.query == "yıllık izin devri"
    assert [(c.id, c.content) for c in evidence.chunks] == [("c1", "Unused leave carries over.")]
    assert evidence.model_context == "Unused leave carries over."
    report_output.assert_not_called()
    assert result["scratch"]["search-1"] == [chunks[0].as_dict()]


@pytest.mark.asyncio
async def test_document_search_falls_back_to_a_summary_when_evidence_is_not_reported():
    chunks = [RagChunk(text="Unused leave carries over.", score=0.9)]
    with patch(f"{_RETRIEVAL}._execute_document_search", AsyncMock(return_value=chunks)):
        _result, _report_evidence, report_output = await _run(
            _spec("DocumentSearch", {"collection": "col-1"}, "documents"), reported=False
        )

    node_id, summary = report_output.call_args.args
    assert node_id == "search-1"
    assert "1 parça getirildi" in summary


@pytest.mark.asyncio
async def test_graph_search_reports_its_subgraph_as_evidence():
    payload = {
        "nodes": [{"id": "a", "name": "Carry-over", "label": "Process"}, {"id": "b", "name": "HR"}],
        "edges": [{"id": "e", "source": "a", "target": "b", "type": "OWNED_BY"}],
        "context": "ctx",
        "seed_node_ids": ["a"],
    }
    with patch(f"{_RETRIEVAL}._execute_graph_search", AsyncMock(return_value=payload)):
        result, report_evidence, report_output = await _run(
            _spec("GraphSearch", {"collection": "g-1"}, "graph_data"), reported=True
        )

    _node_id, evidence = report_evidence.await_args.args
    assert evidence.kind is EvidenceKind.GRAPH
    assert evidence.tool == "graph_search"
    assert [(n.id, n.matched) for n in evidence.graph.nodes] == [("a", True), ("b", False)]
    report_output.assert_not_called()
    assert result["scratch"]["search-1"] == payload


@pytest.mark.asyncio
async def test_a_failure_building_evidence_never_breaks_the_node():
    with (
        patch(f"{_RETRIEVAL}._execute_graph_search", AsyncMock(return_value={"nodes": []})),
        patch(f"{_RETRIEVAL}.graph_evidence", side_effect=ValueError("bad payload")),
    ):
        result, report_evidence, report_output = await _run(
            _spec("GraphSearch", {"collection": "g-1"}, "graph_data"), reported=True
        )

    report_evidence.assert_not_awaited()
    report_output.assert_called_once()
    assert result["scratch"]["search-1"] == {"nodes": []}


@pytest.mark.asyncio
async def test_a_failure_recording_document_evidence_falls_back_to_the_summary():
    chunks = [RagChunk(text="Unused leave carries over.", score=0.9)]
    report_evidence = AsyncMock(side_effect=RuntimeError("recorder down"))
    with (
        patch(f"{_RETRIEVAL}._execute_document_search", AsyncMock(return_value=chunks)),
        patch(f"{_RETRIEVAL}.report_stage_evidence", report_evidence),
        patch(f"{_RETRIEVAL}.report_stage_output") as report_output,
    ):
        graph = await FlowGraphBuilder().build(
            _spec("DocumentSearch", {"collection": "col-1"}, "documents")
        )
        result = await graph.ainvoke({"messages": [HumanMessage(content="q")]})

    report_output.assert_called_once()
    assert result["scratch"]["search-1"] == [chunks[0].as_dict()]
