"""Spec: memory/long_term.py's tunables must come from the config_manager accessor, not be
baked-in literals. Before this, MAX_MEMORY_CONTEXT_CHARS, the extraction
message window, EXTRACTION_TIMEOUT_SECONDS and MAX_CONCURRENT_EXTRACTIONS
were all hardcoded, so tuning any of them per-deployment required a code
change and a release.
"""

import pytest

import memory.long_term as lt
from config_manager import env


def test_context_char_budget_is_sourced_from_settings():
    assert lt.MAX_MEMORY_CONTEXT_CHARS == env.LTM_CONTEXT_MAX_CHARS


def test_extraction_window_is_sourced_from_settings():
    assert lt.EXTRACTION_WINDOW_MESSAGES == env.LTM_EXTRACTION_WINDOW_MESSAGES


def test_extraction_timeout_is_sourced_from_settings():
    assert lt.EXTRACTION_TIMEOUT_SECONDS == env.LTM_EXTRACTION_TIMEOUT_SECONDS


def test_max_concurrent_extractions_is_sourced_from_settings():
    assert lt.MAX_CONCURRENT_EXTRACTIONS == env.LTM_MAX_CONCURRENT_EXTRACTIONS


async def _drain_background_tasks() -> None:
    import asyncio

    if lt._BACKGROUND_TASKS:
        await asyncio.gather(*list(lt._BACKGROUND_TASKS), return_exceptions=True)


class _BoundCapturing:
    def __init__(self, parent: "_CapturingModel") -> None:
        self._parent = parent

    async def ainvoke(self, messages, config=None):
        self._parent.last_prompt = messages[0].content
        return lt.ExtractedFacts(facts=[])


class _CapturingModel:
    def __init__(self) -> None:
        self.last_prompt: str | None = None

    def with_structured_output(self, schema):
        return _BoundCapturing(self)


@pytest.mark.asyncio
async def test_extraction_window_setting_actually_bounds_how_much_history_is_sent(monkeypatch):
    import asyncio

    from langchain_core.messages import HumanMessage

    monkeypatch.setattr(lt, "EXTRACTION_WINDOW_MESSAGES", 2)
    model = _CapturingModel()
    messages = [HumanMessage(content=f"msg-{i}") for i in range(5)]

    await lt.extract_and_save_memories("user-1", messages, model)
    await asyncio.wait_for(_drain_background_tasks(), timeout=1.0)

    assert model.last_prompt is not None
    assert "msg-4" in model.last_prompt
    assert "msg-2" not in model.last_prompt
