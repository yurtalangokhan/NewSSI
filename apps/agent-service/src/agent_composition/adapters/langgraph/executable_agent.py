"""LangGraph executable-agent adapter.

Wraps a compiled LangGraph graph so it satisfies the
``agent_composition.domain.ports.ExecutableAgent`` protocol used by
``ComposedAgent``. The adapter translates between the domain
``AgentRunRequest`` / ``AgentRunResult`` envelope and the raw
``(input, config)`` contract that LangGraph graphs expect.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import Pregel

from agent_composition.domain.ports import (
    AgentChunk,
    AgentEvent,
    AgentRunRequest,
    AgentRunResult,
    AgentState,
    StateRequest,
    StateUpdateRequest,
)


class LangGraphExecutableAgent:
    """Adapter presenting a compiled LangGraph graph as an ``ExecutableAgent``."""

    def __init__(self, graph: CompiledStateGraph | Pregel) -> None:
        self._graph = graph

    @property
    def graph(self) -> CompiledStateGraph | Pregel:
        """The wrapped compiled LangGraph graph (used by legacy callers)."""
        return self._graph

    def _config_from(self, request: AgentRunRequest) -> dict[str, Any] | None:
        settings = request.settings or {}
        return settings.get("config")

    async def ainvoke(self, request: AgentRunRequest) -> AgentRunResult:
        result = await self._graph.ainvoke(request.inputs, config=self._config_from(request))
        return AgentRunResult(output=result, metadata={})

    async def astream(self, request: AgentRunRequest) -> AsyncIterator[AgentChunk]:
        async for chunk in self._graph.astream(request.inputs, config=self._config_from(request)):
            yield AgentChunk(delta=chunk if isinstance(chunk, str) else str(chunk), metadata={})

    async def astream_events(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]:
        async for event in self._graph.astream_events(
            request.inputs, config=self._config_from(request)
        ):
            if isinstance(event, dict):
                yield AgentEvent(name=event.get("event", "unknown"), payload=event)
            else:
                yield AgentEvent(name="unknown", payload={"event": event})

    async def aget_state(self, request: StateRequest) -> AgentState:
        snapshot = await self._graph.aget_state(
            config={"configurable": {"thread_id": request.thread_id}}
        )
        return self._snapshot_to_state(snapshot)

    async def aupdate_state(self, request: StateUpdateRequest) -> AgentState:
        snapshot = await self._graph.aupdate_state(
            config={"configurable": {"thread_id": request.thread_id}},
            values=request.values,
        )
        return self._snapshot_to_state(snapshot)

    async def aget_state_history(self, request: StateRequest) -> AsyncIterator[AgentState]:
        async for snapshot in self._graph.aget_state_history(
            config={"configurable": {"thread_id": request.thread_id}}
        ):
            yield self._snapshot_to_state(snapshot)

    async def close(self) -> None:
        closer = getattr(self._graph, "close", None)
        if callable(closer):
            try:
                await closer()
            except Exception:
                pass

    @staticmethod
    def _snapshot_to_state(snapshot: Any) -> AgentState:
        if isinstance(snapshot, dict):
            values = snapshot.get("values", {})
            metadata = snapshot.get("metadata", {})
        else:
            values = getattr(snapshot, "values", None) or {}
            metadata = getattr(snapshot, "metadata", None) or {}
        return AgentState(values=dict(values), metadata=dict(metadata))
