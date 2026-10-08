"""A retrieval node used as an agent tool reports its evidence on the tool call.

A tool-mode DocumentSearch/GraphSearch runs the node's own function. As a
flow step it announces its evidence as a stage event; as a tool call that
would show the search twice (a raw tool row and a separate card), so the
evidence must instead ride the ToolMessage artifact of the call itself.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from agents.graphs.flow import ResolvedResources, make_component_tool
from agents.graphs.flow.builder import make_node
from integrations.rag_client import RagChunk
from schemas.flows import FlowNode

THREAD_ID = "7f7d8c1e-5e4b-4a57-9c1d-2f6f0d4b9a10"
EVIDENCE_ID = UUID("4f0c3f0e-0a55-4b39-9d2f-54c0a7b1c9e2")


class _Recorder:
    def __init__(self) -> None:
        self.recorded = []

    async def record(self, evidence, *, thread_id=None):
        self.recorded.append(evidence)
        return EVIDENCE_ID


async def _call_tool(node: FlowNode, events: list, recorder: _Recorder):
    tool = make_component_tool(node, ResolvedResources(), node_factory=make_node)
    call = {"name": tool.name, "args": {"query": "izin devri"}, "id": "call-1", "type": "tool_call"}
    builder = StateGraph(MessagesState)
    builder.add_node("tools", ToolNode([tool]))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)

    with (
        patch("agents.graphs.stage_report._stream_writer", return_value=events.append),
        patch("agents.graphs.stage_report.build_knowledge_evidence_recorder", return_value=recorder),
    ):
        output = await builder.compile().ainvoke(
            {"messages": [AIMessage(content="", tool_calls=[call])]},
            config={"configurable": {"thread_id": THREAD_ID}},
        )
    return output["messages"][-1]


@pytest.mark.asyncio
async def test_a_tool_mode_document_search_puts_its_evidence_on_the_tool_message():
    node = FlowNode(id="DocumentSearch-a1b2", type="DocumentSearch", values={"tool_mode": True, "collection": "col-1"})
    events: list = []
    recorder = _Recorder()
    chunks = [RagChunk(text="Kullanılmayan izin devredilir.", score=0.9, metadata={"source": "a.pdf"})]

    with patch("agents.graphs.flow.nodes.retrieval._execute_document_search", AsyncMock(return_value=chunks)):
        message = await _call_tool(node, events, recorder)

    assert message.artifact == {"knowledge_evidence_id": str(EVIDENCE_ID)}
    assert [c.content for c in recorder.recorded[0].chunks] == ["Kullanılmayan izin devredilir."]
    assert [e for e in events if e.get("type") == "flow_stage_evidence"] == []


@pytest.mark.asyncio
async def test_the_model_still_reads_the_same_tool_content():
    node = FlowNode(id="DocumentSearch-a1b2", type="DocumentSearch", values={"tool_mode": True, "collection": "col-1"})
    chunks = [RagChunk(text="Kullanılmayan izin devredilir.", score=0.9)]

    with patch("agents.graphs.flow.nodes.retrieval._execute_document_search", AsyncMock(return_value=chunks)):
        message = await _call_tool(node, [], _Recorder())

    assert "Kullanılmayan izin devredilir." in str(message.content)


@pytest.mark.asyncio
async def test_a_component_tool_without_evidence_has_no_artifact():
    node = FlowNode(
        id="Operations-a1b2",
        type="Operations",
        values={"tool_mode": True, "operation": "Case Conversion", "case_type": "uppercase"},
    )
    tool = make_component_tool(node, ResolvedResources(), node_factory=make_node)
    call = {"name": tool.name, "args": {"text_input": "merhaba"}, "id": "call-2", "type": "tool_call"}

    message = await tool.ainvoke(call)

    assert message.artifact is None


class _SequentialRecorder:
    def __init__(self) -> None:
        self._ids = iter([UUID(int=1), UUID(int=2)])

    async def record(self, evidence, *, thread_id=None):
        return next(self._ids)


@pytest.mark.asyncio
async def test_a_component_reporting_several_evidences_keeps_the_last_and_logs_it():
    from schemas.knowledge_evidence import EvidenceKind, KnowledgeEvidence

    from agents.graphs.stage_report import report_stage_evidence

    evidence = KnowledgeEvidence(kind=EvidenceKind.DOCUMENT, tool="document_search", query="q")

    async def node_factory(node, resources, **_kwargs):
        async def run(state, config):
            recorder = _SequentialRecorder()
            await report_stage_evidence(node.id, evidence, recorder=recorder)
            await report_stage_evidence(node.id, evidence, recorder=recorder)
            return {"scratch": {node.id: "result"}}

        return run

    node = FlowNode(
        id="DocumentSearch-a1b2", type="DocumentSearch", values={"tool_mode": True, "collection": "col-1"}
    )
    tool = make_component_tool(node, ResolvedResources(), node_factory=node_factory)
    call = {"name": tool.name, "args": {"query": "q"}, "id": "call-3", "type": "tool_call"}

    with patch("agents.graphs.flow.nodes.processing.logger") as logger:
        message = await tool.ainvoke(call)

    assert message.artifact == {"knowledge_evidence_id": str(UUID(int=2))}
    logger.warning.assert_called_once()
