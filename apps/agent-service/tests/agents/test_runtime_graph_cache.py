"""The same runtime configuration does not recompile the graph every turn.

``_get_runtime_graph`` rebuilt the whole LangGraph whenever the request
carried any runtime routing key -- and a chat turn always carries ``model``,
so that was every turn of every conversation. Compiling walks the schema,
resolves and binds the tool list and constructs the model, none of which
changes between two turns of the same conversation.

Two things deliberately defeat the cache rather than being keyed on:
``mail_attachments`` (a per-turn payload carrying file bytes, which would
never hit and would pin those bytes in the cache) and ``llm_instance``
(a live object, not a value). Identity keys are part of the key, so one
user's graph is never handed to another.
"""

from __future__ import annotations

from agents.implementations.dynamic_agent import DynamicAgent


def _agent() -> DynamicAgent:
    agent = DynamicAgent.__new__(DynamicAgent)
    agent._config = {"graph_schema": "zero_shot"}
    agent._graph = object()
    agent.builds = 0

    def _build(*, runtime_config=None):
        agent.builds += 1
        return object()

    agent._create_graph_from_config = _build
    return agent


def _config(**configurable):
    return {"configurable": {"model": "gpt-4o", **configurable}}


def test_two_turns_with_the_same_settings_compile_once():
    agent = _agent()

    first = agent._get_runtime_graph(_config())
    second = agent._get_runtime_graph(_config())

    assert first is second
    assert agent.builds == 1


def test_changing_the_model_builds_a_different_graph():
    agent = _agent()

    a = agent._get_runtime_graph(_config())
    b = agent._get_runtime_graph(_config(model="claude-opus-5"))

    assert a is not b
    assert agent.builds == 2


def test_another_users_turn_never_reuses_the_first_users_graph():
    agent = _agent()

    a = agent._get_runtime_graph(_config(user_id="alice"))
    b = agent._get_runtime_graph(_config(user_id="bob"))

    assert a is not b


def test_a_turn_with_attachments_is_not_cached():
    agent = _agent()
    payload = {"mail_attachments": [{"filename": "x.pdf", "content_base64": "eA=="}]}

    first = agent._get_runtime_graph(_config(**payload))
    second = agent._get_runtime_graph(_config(**payload))

    assert first is not second
    assert agent.builds == 2


def test_a_live_model_instance_is_not_cached():
    agent = _agent()
    instance = object()

    first = agent._get_runtime_graph(_config(llm_instance=instance))
    second = agent._get_runtime_graph(_config(llm_instance=instance))

    assert first is not second


def test_a_request_with_no_runtime_keys_still_uses_the_default_graph():
    agent = _agent()

    assert agent._get_runtime_graph({"configurable": {"thread_id": "t1"}}) is agent._graph
    assert agent.builds == 0


def test_the_cache_is_bounded():
    from agents.implementations.dynamic_agent import RUNTIME_GRAPH_CACHE_SIZE

    agent = _agent()
    for index in range(RUNTIME_GRAPH_CACHE_SIZE + 5):
        agent._get_runtime_graph(_config(model=f"model-{index}"))

    assert len(agent._runtime_graphs) <= RUNTIME_GRAPH_CACHE_SIZE
