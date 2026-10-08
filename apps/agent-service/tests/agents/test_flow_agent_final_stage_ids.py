"""FlowAgent.final_stage_node_ids — carried from the builder to the agent."""

from __future__ import annotations

import pytest

from agents.implementations.flow_agent import FlowAgent


@pytest.fixture(autouse=True)
def _fake_model_env(monkeypatch):
    monkeypatch.setenv("USE_FAKE_MODEL", "true")


_SPEC = {
    "nodes": [
        {"id": "in-1", "type": "ChatInput"},
        {"id": "agent-1", "type": "ZeroShotAgent", "values": {"system_prompt": "Be terse."}},
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


@pytest.mark.asyncio
async def test_final_stage_ids_populated_after_load():
    agent = FlowAgent(_SPEC, definition_id="test-def")
    await agent.load()
    assert agent.final_stage_node_ids == {"agent-1"}


@pytest.mark.asyncio
async def test_load_raises_and_leaves_final_stage_ids_empty_when_there_is_no_spec():
    # A load failure must surface as a real error, not a silently degraded
    # fallback graph -- final_stage_node_ids stays empty because nothing
    # ever loaded, not because a placeholder graph reported zero stages.
    agent = FlowAgent(None, definition_id="broken-def")
    with pytest.raises(Exception):
        await agent.load()
    assert agent.final_stage_node_ids == set()


@pytest.mark.asyncio
async def test_final_stage_ids_is_a_copy_not_the_internal_set():
    agent = FlowAgent(_SPEC, definition_id="test-def")
    await agent.load()
    ids = agent.final_stage_node_ids
    ids.add("mutate")
    assert "mutate" not in agent.final_stage_node_ids
