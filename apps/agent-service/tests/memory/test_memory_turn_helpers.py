"""Spec: the recall-then-inject and extract-then-save wiring around a turn
must live in one place. Before this, the same four lines (build an emitter,
call recall_memories, build the context) and the same five lines (build an
emitter, resolve the extract_memory gate, call extract_and_save_memories)
were copy-pasted across chatbot.py, lazy_agent.py (twice), configurable_mcp_agent.py,
graphs/builder.py, composed_agent.py and MemoryPolicy -- a fix to one of them
had to be manually repeated in the rest.
"""

import asyncio

import pytest
from langchain_core.messages import HumanMessage

import memory.long_term as lt


async def _drain_background_tasks() -> None:
    if lt._BACKGROUND_TASKS:
        await asyncio.gather(*list(lt._BACKGROUND_TASKS), return_exceptions=True)


@pytest.mark.asyncio
async def test_recall_context_for_turn_returns_empty_when_facts_recalled_is_empty(monkeypatch):
    async def _fake_recall_memories(user_id, query, *, on_recall=None):
        return {}

    monkeypatch.setattr(lt, "recall_memories", _fake_recall_memories)

    memories, context = await lt.recall_context_for_turn(
        "user-1", "hi", {"long_term_memory": True}
    )

    assert memories == {}
    assert context == ""


@pytest.mark.asyncio
async def test_recall_context_for_turn_builds_the_delimited_context(monkeypatch):
    async def _fake_recall_memories(user_id, query, *, on_recall=None):
        assert user_id == "user-1"
        assert query == "what do I like"
        return {"user_facts": ["User prefers dark mode"]}

    monkeypatch.setattr(lt, "recall_memories", _fake_recall_memories)

    memories, context = await lt.recall_context_for_turn(
        "user-1", "what do I like", {"long_term_memory": True}
    )

    assert memories == {"user_facts": ["User prefers dark mode"]}
    assert "User prefers dark mode" in context
    assert "<user_memory>" in context


@pytest.mark.asyncio
async def test_recall_context_for_turn_passes_on_recall_from_configurable(monkeypatch):
    captured = {}

    async def _fake_recall_memories(user_id, query, *, on_recall=None):
        captured["on_recall"] = on_recall
        return {}

    monkeypatch.setattr(lt, "recall_memories", _fake_recall_memories)

    async def _on_recall(payload):
        pass

    monkeypatch.setattr(
        lt, "build_event_emitters", lambda configurable: (_on_recall, None)
    )

    await lt.recall_context_for_turn("user-1", "hi", {"long_term_memory": True})

    assert captured["on_recall"] is _on_recall


@pytest.mark.asyncio
async def test_extract_memories_for_turn_calls_extract_and_save_with_resolved_gate(monkeypatch):
    captured = {}

    async def _fake_extract(user_id, messages, model, existing_memories=None, *, on_save=None, extract_memory=True):
        captured.update(
            user_id=user_id,
            messages=messages,
            model=model,
            existing_memories=existing_memories,
            extract_memory=extract_memory,
        )

    monkeypatch.setattr(lt, "extract_and_save_memories", _fake_extract)

    messages = [HumanMessage(content="hi")]
    model = object()
    memories = {"user_facts": ["fact"]}

    await lt.extract_memories_for_turn(
        "user-1", {"extract_memory": False}, messages, model, memories
    )

    assert captured == {
        "user_id": "user-1",
        "messages": messages,
        "model": model,
        "existing_memories": memories,
        "extract_memory": False,
    }


@pytest.mark.asyncio
async def test_extract_memories_for_turn_defaults_extract_memory_to_true(monkeypatch):
    captured = {}

    async def _fake_extract(user_id, messages, model, existing_memories=None, *, on_save=None, extract_memory=True):
        captured["extract_memory"] = extract_memory

    monkeypatch.setattr(lt, "extract_and_save_memories", _fake_extract)

    await lt.extract_memories_for_turn("user-1", {}, [], object(), {})

    assert captured["extract_memory"] is True


@pytest.mark.asyncio
async def test_extract_memories_for_turn_is_a_noop_without_a_user_id(monkeypatch):
    called = False

    async def _fake_extract(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(lt, "extract_and_save_memories", _fake_extract)

    await lt.extract_memories_for_turn(None, {}, [], object(), {})

    assert called is False
