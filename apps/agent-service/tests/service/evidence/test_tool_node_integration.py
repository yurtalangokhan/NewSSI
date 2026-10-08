"""A gateway tool inside a real LangGraph ToolNode records evidence under the run's thread."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from agent_composition.adapters.langchain_tool_adapter import LangChainToolAdapter
from agent_composition.domain.ports import ToolDescriptor, ToolResult
from service.knowledge_evidence.artifact_policy import KnowledgeEvidenceArtifactPolicy
from service.knowledge_evidence.recorder import KnowledgeEvidenceRecorder
from service.knowledge_evidence.references import evidence_id_from_artifact

from .conftest import THREAD_ID, make_evidence


@pytest.mark.asyncio
async def test_tool_message_references_evidence_recorded_under_the_thread(store) -> None:
    binding = MagicMock()
    binding.descriptor = ToolDescriptor(key="database_search", description="Search documents")
    binding.invoke = AsyncMock(
        return_value=ToolResult(
            output=[{"type": "text", "text": "[1] (a.pdf)\nUnused leave carries over."}],
            structured=make_evidence().model_dump(mode="json"),
        )
    )
    tool = LangChainToolAdapter(
        binding,
        artifact_policy=KnowledgeEvidenceArtifactPolicy(KnowledgeEvidenceRecorder(store)),
    )
    call = {"name": "database_search", "args": {"query": "leave"}, "id": "call-1", "type": "tool_call"}

    builder = StateGraph(MessagesState)
    builder.add_node("tools", ToolNode([tool]))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)

    output = await builder.compile().ainvoke(
        {"messages": [AIMessage(content="", tool_calls=[call])]},
        config={"configurable": {"thread_id": str(THREAD_ID)}},
    )

    message = output["messages"][-1]
    assert message.content == "[1] (a.pdf)\nUnused leave carries over."
    evidence_id = evidence_id_from_artifact(message.artifact)
    assert store.rows[evidence_id] == (THREAD_ID, make_evidence())
