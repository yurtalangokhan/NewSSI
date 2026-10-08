"""Spec: fact extraction may run on a different model from the conversation.

Extraction asks for something chat does not: write facts in the user's
language, in the third person, and read pronouns correctly. Measured against
the deployed models on a Turkish conversation ("Ben Ali Burak, 2004
doğumluyum..."):

    llama3.1:8b (the chat default)  "Kullanıcı'nın adı Ben Ali Burak."   <- "Ben" read as a name
    qwen3.5:9b                      "Ben Ali Burak is the name of..."    <- fell back to English
    qwen3:8b-fp16                   "Kullanıcının adı Ali Burak'tır."    <- correct
    qwen2.5:14b-instruct            "Kullanıcının adı Ali Burak."        <- correct

The same split showed on Chinese: llama3.1:8b produced malformed text where
the qwen models produced clean sentences. Extraction is a background call, so
pointing it at a better model costs nothing in the response path, and the
conversation keeps whatever model the user picked.

Unset means "use the conversation's model" -- the previous behaviour, and the
right default for a deployment that has only one model pulled.
"""

import asyncio

from config_manager import env
import pytest

import memory.long_term as lt
from infrastructure.llm.llm import UnavailableModel


class _BoundStructuredModel:
    def __init__(self, parent: "_NamedModel") -> None:
        self._parent = parent

    async def ainvoke(self, messages, config=None):
        self._parent.calls += 1
        return lt.ExtractedFacts(language="en", subject="The user", facts=[])


class _NamedModel:
    """A stand-in chat model that records whether extraction used it."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    def with_structured_output(self, schema):
        return _BoundStructuredModel(self)


class _UnresolvableModel(UnavailableModel):
    """What `get_model` returns when the configured name resolves to nothing."""

    def __init__(self) -> None:
        super().__init__(responses=["no provider"])


async def _drain() -> None:
    if lt._BACKGROUND_TASKS:
        await asyncio.wait_for(
            asyncio.gather(*list(lt._BACKGROUND_TASKS), return_exceptions=True), timeout=2.0
        )


async def _noop_save(user_id, facts, **kwargs) -> None:
    """The real save path would do HTTP I/O."""


class _WarningRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def __call__(self, message, *args, **kwargs) -> None:
        self.messages.append(str(message) % args if args else str(message))

    @property
    def text(self) -> str:
        return "\n".join(self.messages).lower()


async def _extract(monkeypatch, turn_model) -> None:
    from langchain_core.messages import HumanMessage

    monkeypatch.setattr(lt, "save_memories", _noop_save)
    await lt.extract_and_save_memories("user-1", [HumanMessage(content="I am 21")], turn_model)
    await _drain()


# ---------------------------------------------------------------------------
# The setting
# ---------------------------------------------------------------------------


def test_the_setting_is_optional_and_defaults_to_unset(monkeypatch) -> None:
    """A deployment with one model pulled must keep working untouched."""
    monkeypatch.delenv("MEMORY_EXTRACTION_MODEL", raising=False)
    assert env.MEMORY_EXTRACTION_MODEL is None


# ---------------------------------------------------------------------------
# Model selection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unset_keeps_using_the_conversations_model(monkeypatch) -> None:
    monkeypatch.delenv("MEMORY_EXTRACTION_MODEL", raising=False)
    turn_model = _NamedModel("chat-model")

    def _must_not_resolve(name):
        raise AssertionError(f"get_model should not be called, got {name!r}")

    monkeypatch.setattr(lt, "get_model", _must_not_resolve)

    await _extract(monkeypatch, turn_model)

    assert turn_model.calls == 1


@pytest.mark.asyncio
async def test_a_blank_setting_is_treated_as_unset(monkeypatch) -> None:
    """An env file with `MEMORY_EXTRACTION_MODEL=` must not resolve `""`."""
    monkeypatch.setenv("MEMORY_EXTRACTION_MODEL", "   ")
    turn_model = _NamedModel("chat-model")

    def _must_not_resolve(name):
        raise AssertionError(f"get_model should not be called, got {name!r}")

    monkeypatch.setattr(lt, "get_model", _must_not_resolve)

    await _extract(monkeypatch, turn_model)

    assert turn_model.calls == 1


@pytest.mark.asyncio
async def test_a_configured_model_is_used_instead_of_the_conversations(monkeypatch) -> None:
    monkeypatch.setenv("MEMORY_EXTRACTION_MODEL", "qwen3:8b-fp16")
    turn_model = _NamedModel("chat-model")
    extraction_model = _NamedModel("qwen3:8b-fp16")
    requested: list[str] = []

    def _resolve(name):
        requested.append(name)
        return extraction_model

    monkeypatch.setattr(lt, "get_model", _resolve)

    await _extract(monkeypatch, turn_model)

    assert requested == ["qwen3:8b-fp16"]
    assert extraction_model.calls == 1
    assert turn_model.calls == 0


@pytest.mark.asyncio
async def test_an_unresolvable_configured_model_falls_back_to_the_conversations(
    monkeypatch,
) -> None:
    """A typo or an unpulled model must not silently stop extraction.

    `get_model` never raises -- it hands back the no-provider placeholder --
    so without this check extraction would "succeed" against a model whose
    only answer is an apology.
    """
    monkeypatch.setenv("MEMORY_EXTRACTION_MODEL", "qwen3:8b-fp16-typo")
    turn_model = _NamedModel("chat-model")
    monkeypatch.setattr(lt, "get_model", lambda _name: _UnresolvableModel())

    warnings = _WarningRecorder()
    monkeypatch.setattr(lt.logger, "warning", warnings)

    await _extract(monkeypatch, turn_model)

    assert turn_model.calls == 1
    assert "qwen3:8b-fp16-typo" in warnings.text


@pytest.mark.asyncio
async def test_a_resolution_failure_falls_back_instead_of_losing_the_turn(
    monkeypatch,
) -> None:
    """Resolution reaches the provider registry, which can fail outright."""
    monkeypatch.setenv("MEMORY_EXTRACTION_MODEL", "qwen3:8b-fp16")
    turn_model = _NamedModel("chat-model")

    def _explode(_name):
        raise RuntimeError("provider registry unreachable")

    monkeypatch.setattr(lt, "get_model", _explode)

    warnings = _WarningRecorder()
    monkeypatch.setattr(lt.logger, "warning", warnings)

    await _extract(monkeypatch, turn_model)

    assert turn_model.calls == 1
    assert "provider registry unreachable" in warnings.text
