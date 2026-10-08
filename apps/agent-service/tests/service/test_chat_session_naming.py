"""Spec: the controller orchestrates naming and records whether the stored
name is final.

Three things this pins down, each of which was broken before:

* The controller owns no prompt and no parsing. It hands the first exchange to
  ``ChatTitleService`` and stores what comes back.
* A name that came from a fallback is stored as ``name_provisional``, so the
  next auto-name attempt replaces it. Without that flag a session named during
  an outage keeps a truncated question forever -- and the frontend's re-name
  trigger (``!chatSession.description``) can never fire, because the listing
  always sends a non-empty description.
* The listing path names unnamed sessions with the same word-boundary
  truncation as everything else. It used to carry its own ``content[:50]``,
  a third title heuristic that cut mid-word.
"""

from copy import deepcopy
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from service.chat.chat_management_service import ChatManagementService
from service.chat.chat_title_service import TitleResult, TitleSource

LONG_QUESTION = (
    "Kubernetes ingress controller'ım sertifikayı yenilemiyor ve tarayıcı sürekli uyarı veriyor"
)


class _ThreadController:
    def __init__(self, thread: dict, messages: list | None = None) -> None:
        self.threads = {thread["thread_id"]: deepcopy(thread)}
        self.messages = messages or []
        self.update_calls: list[dict] = []

    async def get_thread(self, thread_id: str):
        return self.threads.get(thread_id)

    async def get_thread_state(self, thread_id: str):
        return {"values": {"messages": self.messages}}

    async def update_thread(self, thread_id: str, metadata: dict, update_timestamp: bool = True):
        self.update_calls.append({"metadata": deepcopy(metadata)})
        self.threads[thread_id]["metadata"] = deepcopy(metadata)
        return self.threads[thread_id]

    async def list_chat_sessions_by_activity(self, **kwargs):
        return list(deepcopy(self.threads).values())


class _RecordingTitleService:
    """Captures what the controller asked for and replays a fixed answer."""

    def __init__(self, result: TitleResult) -> None:
        self.result = result
        self.sources: list[TitleSource] = []
        self.model_names: list[str | None] = []
        self.llms: list[object | None] = []

    async def generate(self, source, *, model_name=None, llm=None, default_title="New Chat"):
        self.sources.append(source)
        self.model_names.append(model_name)
        self.llms.append(llm)
        return self.result


def _thread(metadata: dict) -> dict:
    return {
        "thread_id": "thread-1",
        "created_at": "2026-09-01T09:00:00+00:00",
        "updated_at": "2026-09-01T09:00:00+00:00",
        "metadata": metadata,
    }


def _controller(threads: _ThreadController, title_service: object) -> ChatManagementService:
    return ChatManagementService(
        thread_service=threads,
        user_id="user-1",
        title_service=title_service,
    )


def _stored_metadata(threads: _ThreadController) -> dict:
    return threads.update_calls[-1]["metadata"]


@pytest.fixture
def _checkpointer():
    with patch("service.chat.chat_management_service.get_checkpointer", return_value=object()):
        yield


@pytest.mark.asyncio
async def test_auto_naming_hands_the_whole_first_exchange_to_the_service(_checkpointer) -> None:
    threads = _ThreadController(
        _thread({"user_id": "user-1", "name": "New Chat"}),
        messages=[
            HumanMessage(content="merhaba"),
            AIMessage(content="Merhaba! Bugün size nasıl yardımcı olabilirim?"),
        ],
    )
    service = _RecordingTitleService(TitleResult("Selamlaşma", provisional=False))

    await _controller(threads, service).rename_chat_session("thread-1", None)

    assert service.sources[0].user_message == "merhaba"
    assert "nasıl yardımcı olabilirim" in service.sources[0].assistant_message


@pytest.mark.asyncio
async def test_a_final_title_is_stored_without_the_provisional_flag(_checkpointer) -> None:
    threads = _ThreadController(
        _thread({"user_id": "user-1", "name": "New Chat"}),
        messages=[HumanMessage(content=LONG_QUESTION)],
    )
    service = _RecordingTitleService(TitleResult("Ingress sertifika yenileme", provisional=False))

    await _controller(threads, service).rename_chat_session("thread-1", None)

    stored = _stored_metadata(threads)
    assert stored["name"] == "Ingress sertifika yenileme"
    assert "name_provisional" not in stored


@pytest.mark.asyncio
async def test_a_fallback_title_is_flagged_for_a_later_retry(_checkpointer) -> None:
    threads = _ThreadController(
        _thread({"user_id": "user-1", "name": "New Chat"}),
        messages=[HumanMessage(content=LONG_QUESTION)],
    )
    service = _RecordingTitleService(
        TitleResult("Kubernetes ingress controller'ım…", provisional=True, reason="no_model")
    )

    await _controller(threads, service).rename_chat_session("thread-1", None)

    stored = _stored_metadata(threads)
    assert stored["name"] == "Kubernetes ingress controller'ım…"
    assert stored["name_provisional"] is True


@pytest.mark.asyncio
async def test_a_later_attempt_clears_the_flag_once_it_succeeds(_checkpointer) -> None:
    threads = _ThreadController(
        _thread({"user_id": "user-1", "name": "Kubernetes ingress…", "name_provisional": True}),
        messages=[HumanMessage(content=LONG_QUESTION)],
    )
    service = _RecordingTitleService(TitleResult("Ingress sertifika yenileme", provisional=False))

    await _controller(threads, service).rename_chat_session("thread-1", None)

    stored = _stored_metadata(threads)
    assert stored["name"] == "Ingress sertifika yenileme"
    assert "name_provisional" not in stored


@pytest.mark.asyncio
async def test_a_manual_rename_is_final_and_never_calls_the_model(_checkpointer) -> None:
    threads = _ThreadController(
        _thread({"user_id": "user-1", "name": "Kubernetes ingress…", "name_provisional": True}),
        messages=[HumanMessage(content=LONG_QUESTION)],
    )
    service = _RecordingTitleService(TitleResult("unused", provisional=False))

    await _controller(threads, service).rename_chat_session("thread-1", "  Sertifika işi  ")

    stored = _stored_metadata(threads)
    assert stored["name"] == "Sertifika işi"
    assert "name_provisional" not in stored
    assert service.sources == []


@pytest.mark.asyncio
async def test_the_model_the_session_runs_on_is_used_for_its_title(_checkpointer) -> None:
    threads = _ThreadController(
        _thread({"user_id": "user-1", "name": "New Chat", "current_alternate_model": "qwen3:8b"}),
        messages=[HumanMessage(content=LONG_QUESTION)],
    )
    service = _RecordingTitleService(TitleResult("Ingress sertifikası", provisional=False))

    await _controller(threads, service).rename_chat_session("thread-1", None)

    assert service.model_names == ["qwen3:8b"]


@pytest.mark.asyncio
async def test_the_listing_reports_whether_a_name_is_provisional(_checkpointer) -> None:
    threads = _ThreadController(
        _thread({"user_id": "user-1", "name": "Kubernetes ingress…", "name_provisional": True})
    )
    service = _RecordingTitleService(TitleResult("unused", provisional=False))

    listing = await _controller(threads, service).get_chat_sessions()

    assert listing["sessions"][0]["name_provisional"] is True


@pytest.mark.asyncio
async def test_a_settled_name_is_not_reported_as_provisional(_checkpointer) -> None:
    threads = _ThreadController(_thread({"user_id": "user-1", "name": "Ingress sertifikası"}))
    service = _RecordingTitleService(TitleResult("unused", provisional=False))

    listing = await _controller(threads, service).get_chat_sessions()

    assert listing["sessions"][0]["name_provisional"] is False


@pytest.mark.asyncio
async def test_the_listing_never_cuts_a_word_in_half(_checkpointer) -> None:
    """The old listing path sliced `content[:50]`, landing mid-word."""
    threads = _ThreadController(
        _thread({"user_id": "user-1", "name": "New Chat"}),
        messages=[HumanMessage(content=LONG_QUESTION)],
    )
    service = _RecordingTitleService(TitleResult("unused", provisional=False))

    listing = await _controller(threads, service).get_chat_sessions()
    name = listing["sessions"][0]["name"]

    assert LONG_QUESTION.startswith(name.rstrip("…"))
    assert name.rstrip("…").split()[-1] in LONG_QUESTION.split()


@pytest.mark.asyncio
async def test_the_listing_does_not_call_the_model(_checkpointer) -> None:
    """One LLM call per listed row would make opening the sidebar the most
    expensive request in the app."""
    threads = _ThreadController(
        _thread({"user_id": "user-1", "name": "New Chat"}),
        messages=[HumanMessage(content=LONG_QUESTION)],
    )
    service = _RecordingTitleService(TitleResult("unused", provisional=False))

    await _controller(threads, service).get_chat_sessions()

    assert service.sources == []


@pytest.mark.asyncio
async def test_a_session_that_was_never_named_is_reported_as_provisional(_checkpointer) -> None:
    """A thread with no stored name has not been through naming at all.

    The listing substitutes "New Chat" for it, which is indistinguishable from
    a settled title on the wire. Reporting it as provisional is what lets the
    client ask for a real one -- otherwise the session keeps the placeholder
    until someone renames it by hand.
    """
    threads = _ThreadController(_thread({"user_id": "user-1"}))
    service = _RecordingTitleService(TitleResult("unused", provisional=False))

    listing = await _controller(threads, service).get_chat_sessions()

    assert listing["sessions"][0]["name_provisional"] is True


_EXCHANGE = [HumanMessage(content="merhaba"), AIMessage(content="Merhaba!")]
_GEMINI_THREAD = {
    "user_id": "user-1",
    "name": "New Chat",
    "current_alternate_model": "gemini-3.8-flash",
    "current_alternate_provider_id": "provider-1",
    "current_alternate_provider_type": "google_genai",
}


@pytest.mark.asyncio
async def test_naming_uses_the_provider_client_the_chat_used(_checkpointer) -> None:
    live_llm = object()
    threads = _ThreadController(_thread(dict(_GEMINI_THREAD)), messages=_EXCHANGE)
    service = _RecordingTitleService(TitleResult("Selamlaşma", provisional=False))

    with patch(
        "service.chat.session_naming_service.resolve_provider_llm", return_value=live_llm
    ) as resolve:
        await _controller(threads, service).rename_chat_session("thread-1", None)

    resolve.assert_awaited_once_with(
        model_name="gemini-3.8-flash",
        provider_id="provider-1",
        provider_type="google_genai",
        user_id="user-1",
    )
    assert service.llms == [live_llm]


@pytest.mark.asyncio
async def test_naming_never_sends_a_provider_model_name_to_the_local_fallback(_checkpointer) -> None:
    threads = _ThreadController(_thread(dict(_GEMINI_THREAD)), messages=_EXCHANGE)
    service = _RecordingTitleService(TitleResult("Selamlaşma", provisional=False))

    with patch(
        "service.chat.session_naming_service.resolve_provider_llm", side_effect=RuntimeError("no key")
    ):
        await _controller(threads, service).rename_chat_session("thread-1", None)

    assert service.model_names == [None]
    assert service.llms == [None]
    assert _stored_metadata(threads)["name"] == "Selamlaşma"


@pytest.mark.asyncio
async def test_naming_without_a_stored_provider_is_unchanged(_checkpointer) -> None:
    threads = _ThreadController(
        _thread({"user_id": "user-1", "name": "New Chat", "current_alternate_model": "llama3.1:8b"}),
        messages=_EXCHANGE,
    )
    service = _RecordingTitleService(TitleResult("Selamlaşma", provisional=False))

    with patch("service.chat.session_naming_service.resolve_provider_llm") as resolve:
        await _controller(threads, service).rename_chat_session("thread-1", None)

    resolve.assert_not_called()
    assert service.model_names == ["llama3.1:8b"]
    assert service.llms == [None]


@pytest.mark.asyncio
async def test_switching_the_model_alone_forgets_the_old_provider() -> None:
    threads = _ThreadController(_thread(dict(_GEMINI_THREAD)))

    await _controller(threads, _RecordingTitleService(TitleResult("x", provisional=False))).update_chat_session_model(
        "thread-1", "llama3.1:8b"
    )

    stored = _stored_metadata(threads)
    assert stored["current_alternate_model"] == "llama3.1:8b"
    assert "current_alternate_provider_id" not in stored
    assert "current_alternate_provider_type" not in stored


@pytest.mark.asyncio
async def test_an_empty_model_update_keeps_the_provider() -> None:
    threads = _ThreadController(_thread(dict(_GEMINI_THREAD)))

    await _controller(threads, _RecordingTitleService(TitleResult("x", provisional=False))).update_chat_session_model(
        "thread-1", None
    )

    assert _stored_metadata(threads)["current_alternate_provider_id"] == "provider-1"
