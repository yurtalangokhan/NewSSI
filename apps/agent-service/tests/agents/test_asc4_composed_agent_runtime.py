from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from agent_composition.domain.ports import (
    AgentChunk,
    AgentEvent,
    AgentRunRequest,
    AgentRunResult,
    AgentState,
    StateRequest,
    StateUpdateRequest,
)
from agent_composition.runtime import ComposedAgent, RetryPolicy, RetryPolicyConfig


class RecordingExecutableAgent:
    def __init__(self) -> None:
        self.stream_request: AgentRunRequest | None = None
        self.event_request: AgentRunRequest | None = None

    async def ainvoke(self, request: AgentRunRequest) -> AgentRunResult:
        return AgentRunResult(output=request.inputs)

    async def astream(self, request: AgentRunRequest) -> AsyncIterator[AgentChunk]:
        self.stream_request = request
        yield AgentChunk(delta="ok", metadata={"seen": request.inputs})

    async def astream_events(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]:
        self.event_request = request
        yield AgentEvent(name="on_chain_stream", payload={"seen": request.inputs})

    async def aget_state(self, request: StateRequest) -> AgentState:
        return AgentState(values={"thread_id": request.thread_id})

    async def aupdate_state(self, request: StateUpdateRequest) -> AgentState:
        return AgentState(values=request.values)

    async def aget_state_history(self, request: StateRequest) -> AsyncIterator[AgentState]:
        yield AgentState(values={"thread_id": request.thread_id})

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_composed_agent_stream_uses_memory_enriched_request(monkeypatch: pytest.MonkeyPatch):
    executable = RecordingExecutableAgent()
    agent = ComposedAgent(executable_agent=executable)
    await agent.load()

    async def fake_inject(input_data: Any, config: Any = None):
        return {"messages": ["enriched"]}, {}, None

    monkeypatch.setattr(agent, "_inject_memory_into_input", fake_inject)

    chunks = [
        chunk
        async for chunk in agent.astream(
            AgentRunRequest(
                inputs={"messages": ["original"]},
                settings={"config": {"configurable": {"thread_id": "t1"}}},
            )
        )
    ]

    assert chunks
    assert executable.stream_request is not None
    assert executable.stream_request.inputs == {"messages": ["enriched"]}


@pytest.mark.asyncio
async def test_composed_agent_events_use_memory_enriched_request(monkeypatch: pytest.MonkeyPatch):
    executable = RecordingExecutableAgent()
    agent = ComposedAgent(executable_agent=executable)
    await agent.load()

    async def fake_inject(input_data: Any, config: Any = None):
        return {"messages": ["enriched"]}, {}, None

    monkeypatch.setattr(agent, "_inject_memory_into_input", fake_inject)

    events = [
        event
        async for event in agent.astream_events(
            AgentRunRequest(
                inputs={"messages": ["original"]},
                settings={"config": {"configurable": {"thread_id": "t1"}}},
            )
        )
    ]

    assert events
    assert executable.event_request is not None
    assert executable.event_request.inputs == {"messages": ["enriched"]}


@pytest.mark.asyncio
async def test_retry_policy_uses_fresh_coroutine_for_each_retry():
    policy = RetryPolicy(
        RetryPolicyConfig(
            enabled=True,
            max_attempts=2,
            initial_delay=0,
            max_delay=0,
        )
    )
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient")
        return "ok"

    assert await policy.run_with_retry(operation, operation_name="unit") == "ok"
    assert attempts == 2
