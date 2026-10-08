"""Spec: a thread remembers which provider its model belongs to.

Without the provider, a later step that only has the thread (auto-naming) can
find just a model name -- and a bare ``gemini-...`` name gets answered by the
Ollama fallback.
"""

import pytest

from service.chat.chat_thread_service import prepare_chat_thread


class _Threads:
    def __init__(self, metadata: dict | None = None) -> None:
        self.thread = {"thread_id": "t1", "metadata": metadata} if metadata is not None else None
        self.updated: dict | None = None

    async def get_thread(self, thread_id):
        return self.thread

    async def create_thread(self, thread_id, metadata):
        self.thread = {"thread_id": thread_id, "metadata": metadata}
        return self.thread

    async def update_thread(self, thread_id, metadata, **kwargs):
        self.updated = dict(metadata)
        self.thread["metadata"] = metadata
        return self.thread


async def _prepare(threads: _Threads, llm_override: dict | None) -> None:
    await prepare_chat_thread(
        threads,
        session_id="t1",
        session_name="Sohbet",
        effective_user_id="user-1",
        known_user_ids={"user-1"},
        persona_id=0,
        project_id=None,
        llm_override=llm_override,
    )


@pytest.mark.asyncio
async def test_the_provider_is_stored_next_to_the_model() -> None:
    threads = _Threads({"user_id": "user-1", "name": "Sohbet"})

    await _prepare(
        threads,
        {"model": "gemini-3.8-flash", "provider_id": "provider-1", "provider_type": "google_genai"},
    )

    assert threads.updated["current_alternate_model"] == "gemini-3.8-flash"
    assert threads.updated["current_alternate_provider_id"] == "provider-1"
    assert threads.updated["current_alternate_provider_type"] == "google_genai"


@pytest.mark.asyncio
async def test_a_model_without_a_provider_clears_the_previous_provider() -> None:
    threads = _Threads(
        {
            "user_id": "user-1",
            "name": "Sohbet",
            "current_alternate_model": "gemini-3.8-flash",
            "current_alternate_provider_id": "provider-1",
            "current_alternate_provider_type": "google_genai",
        }
    )

    await _prepare(threads, {"model": "llama3.1:8b"})

    assert threads.updated["current_alternate_model"] == "llama3.1:8b"
    assert "current_alternate_provider_id" not in threads.updated
    assert "current_alternate_provider_type" not in threads.updated
