"""The manifest reaches the model on both agent factories, per call, and never lands in state."""

from __future__ import annotations

from uuid import uuid4

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
import pytest

from agents.graphs.middleware import AttachmentManifestMiddleware
from agents.tooling import attachment_manifest as manifest
from core.types.authored_documents import AttachmentImageInfo

CONFIG = {"configurable": {"user_id": "u1", "thread_id": str(uuid4())}}


class SpyModel(GenericFakeChatModel):
    """Records the messages of every call it receives."""

    seen: list = []

    async def _agenerate(self, messages, *args, **kwargs):
        self.seen.append(list(messages))
        return await super()._agenerate(messages, *args, **kwargs)


def _spy() -> SpyModel:
    return SpyModel(messages=iter([AIMessage(content="ok")]), seen=[])


class Store:
    def __init__(self, *file_ids: str):
        self.file_ids = list(file_ids)

    async def list_for_thread(self, user_id, thread_id):
        return [AttachmentImageInfo(file_id=i, filename=f"{i}.jpg", mime_type="image/jpeg") for i in self.file_ids]


def _system_text(messages) -> str:
    system = [m for m in messages if isinstance(m, SystemMessage)]
    assert len(system) == 1, "exactly one system message expected"
    return system[0].content


def _no_system_in_state(result) -> bool:
    return not any(isinstance(m, SystemMessage) for m in result["messages"])


async def _run_react(store: Store, monkeypatch) -> tuple[str, dict]:
    monkeypatch.setattr(manifest, "attachment_store", lambda: store)
    model = _spy()
    agent = create_react_agent(model, [], prompt=manifest.attachment_aware_prompt("BASE"))
    result = await agent.ainvoke({"messages": [HumanMessage(content="hi")]}, CONFIG)
    return _system_text(model.seen[0]), result


async def _run_agent(store: Store, monkeypatch) -> tuple[str, dict]:
    monkeypatch.setattr(manifest, "attachment_store", lambda: store)
    model = _spy()
    agent = create_agent(model, [], system_prompt="BASE", middleware=[AttachmentManifestMiddleware()])
    result = await agent.ainvoke({"messages": [HumanMessage(content="hi")]}, CONFIG)
    return _system_text(model.seen[0]), result


@pytest.mark.asyncio
@pytest.mark.parametrize("run", [_run_react, _run_agent], ids=["create_react_agent", "create_agent"])
async def test_the_model_sees_the_attached_image_id_and_state_stays_clean(run, monkeypatch) -> None:
    system, result = await run(Store("f1"), monkeypatch)

    assert system.startswith("BASE")
    assert "attachment:f1" in system
    assert _no_system_in_state(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("run", [_run_react, _run_agent], ids=["create_react_agent", "create_agent"])
async def test_a_chat_without_images_keeps_the_prompt_exactly(run, monkeypatch) -> None:
    system, _ = await run(Store(), monkeypatch)

    assert system == "BASE"


@pytest.mark.asyncio
async def test_the_list_is_read_on_every_call_not_frozen_at_build_time(monkeypatch) -> None:
    """A cached graph must see an image attached after it was built."""
    store = Store("f1")
    monkeypatch.setattr(manifest, "attachment_store", lambda: store)
    first, second = _spy(), _spy()
    prompt = manifest.attachment_aware_prompt("BASE")
    agent_one = create_react_agent(first, [], prompt=prompt)
    agent_two = create_react_agent(second, [], prompt=prompt)

    await agent_one.ainvoke({"messages": [HumanMessage(content="hi")]}, CONFIG)
    store.file_ids.append("f2")
    await agent_two.ainvoke({"messages": [HumanMessage(content="hi")]}, CONFIG)

    assert "attachment:f2" not in _system_text(first.seen[0])
    assert "attachment:f2" in _system_text(second.seen[0])


@pytest.mark.asyncio
async def test_the_middleware_adds_a_manifest_to_a_graph_without_a_base_prompt(monkeypatch) -> None:
    monkeypatch.setattr(manifest, "attachment_store", lambda: Store("f1"))
    model = _spy()
    agent = create_agent(model, [], middleware=[AttachmentManifestMiddleware()])

    await agent.ainvoke({"messages": [HumanMessage(content="hi")]}, CONFIG)

    system = _system_text(model.seen[0])
    assert system.startswith("Images the user attached") and "attachment:f1" in system


@pytest.mark.asyncio
async def test_a_storage_failure_does_not_fail_the_model_call(monkeypatch) -> None:
    class Broken:
        async def list_for_thread(self, *_):
            raise RuntimeError("db down")

    monkeypatch.setattr(manifest, "attachment_store", lambda: Broken())
    model = _spy()
    agent = create_agent(model, [], system_prompt="BASE", middleware=[AttachmentManifestMiddleware()])

    result = await agent.ainvoke({"messages": [HumanMessage(content="hi")]}, CONFIG)

    assert _system_text(model.seen[0]) == "BASE"
    assert result["messages"][-1].content == "ok"
