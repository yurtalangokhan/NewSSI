import asyncio
from copy import deepcopy
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from service.chat.chat_title_service import TitleResult
from service.chat.session_naming_service import (
    LocalNamingLock,
    NamingOutcome,
    SessionNamingService,
)
from service.chat.session_title_hook import SessionTitleHook
from service.chat_runs.domain import ChatRun, ChatRunSpec

pytestmark = pytest.mark.asyncio


class _Threads:
    def __init__(self, metadata: dict) -> None:
        self.thread = {"thread_id": "t1", "metadata": deepcopy(metadata)}
        self.messages = [HumanMessage("Kubernetes ingress sertifika"), AIMessage("Şöyle yapın...")]

    async def get_thread(self, thread_id):
        return deepcopy(self.thread) if thread_id == "t1" else None

    async def get_thread_state(self, thread_id):
        return {"values": {"messages": self.messages}}

    async def update_thread(self, thread_id, metadata, update_timestamp=True):
        self.thread["metadata"] = deepcopy(metadata)


class _Titles:
    def __init__(self, result=TitleResult("Ingress Sertifikası", provisional=False), delay=0.0, on_generate=None):
        self.result, self.delay, self.on_generate, self.calls = result, delay, on_generate, 0

    async def generate(self, source, *, model_name=None, llm=None, default_title="New Chat"):
        self.calls += 1
        if self.on_generate:
            await self.on_generate()
        await asyncio.sleep(self.delay)
        return self.result


@pytest.fixture(autouse=True)
def _checkpointer():
    with patch("service.chat.session_naming_service.get_checkpointer", return_value=object()):
        yield


def _service(threads, titles, **kwargs):
    return SessionNamingService(
        thread_service=threads, title_service=titles, lock=LocalNamingLock(), poll_seconds=0.01, **kwargs
    )


async def test_hook_names_a_session_whose_client_went_away():
    threads, titles = _Threads({"name": "Kubernetes ingress", "name_source": "seed"}), _Titles()
    hook = SessionTitleHook(lambda: _service(threads, titles))
    run = ChatRun.start(run_id="r1", spec=ChatRunSpec("t1", "u1"), instance_id="i", now=1.0)
    await hook.on_run_completed(run)
    meta = threads.thread["metadata"]
    assert (meta["name"], meta["name_source"]) == ("Ingress Sertifikası", "auto")
    assert "name_provisional" not in meta


async def test_a_second_completion_does_not_call_the_model_again():
    threads, titles = _Threads({"name": "x", "name_source": "seed"}), _Titles()
    naming = _service(threads, titles)
    assert await naming.ensure_named("t1") is NamingOutcome.NAMED
    assert await naming.ensure_named("t1") is NamingOutcome.ALREADY_NAMED
    assert titles.calls == 1


async def test_hook_and_client_rename_racing_call_the_model_once():
    threads, titles = _Threads({"name": "x", "name_source": "seed"}), _Titles(delay=0.1)
    naming = _service(threads, titles)
    outcomes = await asyncio.gather(
        naming.ensure_named("t1"), naming.ensure_named("t1", respect_legacy=False)
    )
    assert sorted(outcomes) == sorted([NamingOutcome.NAMED, NamingOutcome.WAITED])
    assert titles.calls == 1


async def test_a_user_rename_during_generation_wins():
    threads = _Threads({"name": "x", "name_source": "seed"})

    async def user_renames():
        threads.thread["metadata"].update(name="Benim adım", name_source="user")

    naming = _service(threads, _Titles(on_generate=user_renames))
    await naming.ensure_named("t1")
    assert threads.thread["metadata"]["name"] == "Benim adım"


async def test_a_fallback_title_is_provisional_and_retried_next_completion():
    threads = _Threads({"name": "x", "name_source": "seed"})
    flaky = _Titles(result=TitleResult("x", provisional=True, reason="llm_error"))
    naming = _service(threads, flaky)
    await naming.ensure_named("t1")
    assert threads.thread["metadata"]["name_provisional"] is True
    flaky.result = TitleResult("Kalıcı Başlık", provisional=False)
    assert await naming.ensure_named("t1") is NamingOutcome.NAMED
    assert "name_provisional" not in threads.thread["metadata"]


async def test_legacy_named_sessions_are_left_alone_by_the_hook_only():
    threads, titles = _Threads({"name": "Old manual name"}), _Titles()
    naming = _service(threads, titles)
    assert await naming.ensure_named("t1") is NamingOutcome.ALREADY_NAMED
    assert await naming.ensure_named("t1", respect_legacy=False) is NamingOutcome.NAMED


async def test_missing_session_is_reported():
    naming = _service(_Threads({}), _Titles())
    assert await naming.ensure_named("nope") is NamingOutcome.MISSING
