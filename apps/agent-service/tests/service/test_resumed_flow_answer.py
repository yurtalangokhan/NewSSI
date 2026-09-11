"""A FlowAgent turn that resumes from a HumanInput/interrupt and then goes
straight to ChatOutput streams no new tokens — `_emit_resumed_flow_answer`
replays the answer already in state so the turn is not silently empty.

The bug this pins: after clicking a HumanInput decision the run finished but
the client saw nothing; the real answer (produced before the pause) only
appeared on a page reload.
"""

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage
from langgraph.types import Command

from agents.flow_agent import FlowAgent
from service.AgentStreamService import _emit_resumed_flow_answer


class _FakeFlowAgent(FlowAgent):
    def __init__(self, state):
        self._state = state

    async def aget_state(self, config=None, **kwargs):
        return self._state


def _ctx(**over):
    base = dict(
        emitted_ai_message_ids=set(),
        streamed_message_ids=set(),
        run_id="run-1",
    )
    base.update(over)
    return SimpleNamespace(**base)


def _state(messages, tasks=()):
    return SimpleNamespace(values={"messages": messages}, tasks=tasks)


_ANSWER = AIMessage(content="✅ E-posta gönderildi", id="ai-final")
_RESUME = {"input": Command(resume="Onayla"), "config": {"configurable": {"thread_id": "t1"}}}


async def _run(agent, ctx, kwargs):
    return [chunk async for chunk in _emit_resumed_flow_answer(ctx, agent, kwargs)]


@pytest.mark.asyncio
async def test_replays_the_pre_pause_answer_when_the_resume_streamed_nothing():
    agent = _FakeFlowAgent(
        _state(
            [
                AIMessage(
                    content="",
                    id="ai-mid",
                    tool_calls=[{"name": "send_email", "args": {}, "id": "c1"}],
                ),
                _ANSWER,
            ]
        )
    )

    out = await _run(agent, _ctx(), _RESUME)

    assert len(out) == 1
    packet = json.loads(out[0][len("data: ") :].strip())
    assert packet["type"] == "message"
    assert packet["content"]["content"] == "✅ E-posta gönderildi"


@pytest.mark.asyncio
async def test_stays_silent_when_the_resume_hit_a_fresh_interrupt():
    parked = SimpleNamespace(interrupts=[object()])
    agent = _FakeFlowAgent(_state([_ANSWER], tasks=(parked,)))

    assert await _run(agent, _ctx(), _RESUME) == []


@pytest.mark.asyncio
async def test_stays_silent_on_a_normal_first_run_not_a_resume():
    agent = _FakeFlowAgent(_state([_ANSWER]))
    kwargs = {"input": {"messages": []}, "config": {}}

    assert await _run(agent, _ctx(), kwargs) == []


@pytest.mark.asyncio
async def test_does_not_double_emit_a_message_this_run_already_showed():
    agent = _FakeFlowAgent(_state([_ANSWER]))

    out = await _run(agent, _ctx(emitted_ai_message_ids={"ai-final"}), _RESUME)

    assert out == []


@pytest.mark.asyncio
async def test_ignores_a_non_flow_agent():
    assert await _run(object(), _ctx(), _RESUME) == []
