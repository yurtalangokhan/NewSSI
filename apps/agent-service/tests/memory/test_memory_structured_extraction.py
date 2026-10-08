"""Spec: fact extraction must use the model's structured-output contract
instead of hand-parsing raw text as JSON. Before this, `_extract_and_save_memories_impl`
called `response.content.strip()` then `json.loads(...)` with manual
markdown-fence stripping -- any deviation in the model's raw text (a stray
sentence, a differently-fenced block, non-JSON prose) silently dropped the
whole turn's extraction with only a warning log.
"""

import asyncio

import pytest
from langchain_core.messages import HumanMessage

import memory.long_term as lt


async def _drain_background_tasks() -> None:
    if lt._BACKGROUND_TASKS:
        await asyncio.gather(*list(lt._BACKGROUND_TASKS), return_exceptions=True)


class _BoundStructuredModel:
    """What `model.with_structured_output(Schema)` returns: a runnable whose
    ainvoke yields a schema instance instead of a raw AIMessage."""

    def __init__(self, parent: "_StructuredFakeModel") -> None:
        self._parent = parent

    async def ainvoke(self, messages, config=None):
        self._parent.last_prompt = messages[0].content
        self._parent.last_config = config
        if self._parent.raises is not None:
            raise self._parent.raises
        return self._parent.result


class _StructuredFakeModel:
    """Fake chat model exposing the with_structured_output contract."""

    def __init__(self, result=None, raises: Exception | None = None) -> None:
        self.result = result
        self.raises = raises
        self.last_prompt: str | None = None
        self.last_config: dict | None = None
        self.requested_schema = None

    def with_structured_output(self, schema):
        self.requested_schema = schema
        return _BoundStructuredModel(self)


@pytest.mark.asyncio
async def test_extraction_saves_facts_from_structured_output(monkeypatch):
    saved: dict = {}

    async def _fake_save_memories(user_id, facts, *, language="", on_save=None):
        saved["facts"] = facts

    monkeypatch.setattr(lt, "save_memories", _fake_save_memories)

    model = _StructuredFakeModel(result=lt.ExtractedFacts(language="en", subject="The user", facts=["User's name is Alice"]))
    messages = [HumanMessage(content="My name is Alice")]

    await lt.extract_and_save_memories("user-1", messages, model)
    await asyncio.wait_for(_drain_background_tasks(), timeout=1.0)

    assert saved["facts"] == ["User's name is Alice"]
    assert model.requested_schema is lt.ExtractedFacts


@pytest.mark.asyncio
async def test_extraction_filters_blank_facts_from_structured_output(monkeypatch):
    saved: dict = {}

    async def _fake_save_memories(user_id, facts, *, language="", on_save=None):
        saved["facts"] = facts

    monkeypatch.setattr(lt, "save_memories", _fake_save_memories)

    model = _StructuredFakeModel(result=lt.ExtractedFacts(language="en", subject="The user", facts=["  ", "Real fact", ""]))
    messages = [HumanMessage(content="hi")]

    await lt.extract_and_save_memories("user-1", messages, model)
    await asyncio.wait_for(_drain_background_tasks(), timeout=1.0)

    assert saved["facts"] == ["Real fact"]


@pytest.mark.asyncio
async def test_extraction_with_no_facts_does_not_save(monkeypatch):
    called = False

    async def _fake_save_memories(user_id, facts, *, language="", on_save=None):
        nonlocal called
        called = True

    monkeypatch.setattr(lt, "save_memories", _fake_save_memories)

    model = _StructuredFakeModel(result=lt.ExtractedFacts(language="en", subject="The user", facts=[]))
    messages = [HumanMessage(content="hi")]

    await lt.extract_and_save_memories("user-1", messages, model)
    await asyncio.wait_for(_drain_background_tasks(), timeout=1.0)

    assert called is False


@pytest.mark.asyncio
async def test_structured_output_error_does_not_raise_or_hang():
    model = _StructuredFakeModel(raises=ValueError("model refused to comply with schema"))
    messages = [HumanMessage(content="hi")]

    await lt.extract_and_save_memories("user-1", messages, model)

    # Must complete (not hang) and must not propagate -- extraction failures
    # are fail-open by design so a bad model response can't break the chat.
    await asyncio.wait_for(_drain_background_tasks(), timeout=1.0)
