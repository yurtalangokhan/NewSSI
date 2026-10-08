"""list_attachments: how the model learns the file ids of images attached to this chat."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from agents.tooling import document_workspace_tools as tools
from agents.tooling.document_tools import DOCUMENT_TOOL_PROMPT, get_document_tools
from core.types.authored_documents import AttachmentImageInfo

THREAD = uuid4()
CONFIG = {"configurable": {"user_id": "u1", "thread_id": str(THREAD)}}


class FakeStore:
    def __init__(self, images=()):
        self.images = list(images)
        self.requests: list[tuple[str, object]] = []

    async def list_for_thread(self, user_id, thread_id):
        self.requests.append((user_id, thread_id))
        return self.images


@pytest.mark.asyncio
async def test_lists_the_thread_images_with_their_ids(monkeypatch) -> None:
    store = FakeStore([AttachmentImageInfo("f1", "diagram.png", "image/png")])
    monkeypatch.setattr(tools, "attachment_store", lambda: store)

    payload = json.loads(await tools.list_attachments.ainvoke({}, CONFIG))

    assert payload["attachments"] == [
        {
            "file_id": "f1",
            "filename": "diagram.png",
            "mime_type": "image/png",
            "markdown": "![diagram.png](attachment:f1)",
        }
    ]
    assert store.requests == [("u1", THREAD)]


@pytest.mark.asyncio
async def test_without_a_thread_there_is_nothing_to_list(monkeypatch) -> None:
    monkeypatch.setattr(tools, "attachment_store", lambda: pytest.fail("must not query storage"))

    payload = json.loads(await tools.list_attachments.ainvoke({}, {"configurable": {"user_id": "u1"}}))

    assert payload == {"attachments": []}


@pytest.mark.asyncio
async def test_a_run_without_a_user_is_refused() -> None:
    result = await tools.list_attachments.ainvoke({}, {"configurable": {}})

    assert result.startswith("Error:")


@pytest.mark.asyncio
async def test_a_storage_failure_is_reported_without_internals(monkeypatch) -> None:
    class Broken:
        async def list_for_thread(self, user_id, thread_id):
            raise RuntimeError("db password=secret")

    monkeypatch.setattr(tools, "attachment_store", lambda: Broken())

    result = await tools.list_attachments.ainvoke({}, CONFIG)

    assert result.startswith("Error:") and "secret" not in result


def test_the_tool_is_registered_and_the_prompt_explains_the_syntax() -> None:
    assert "list_attachments" in {tool.name for tool in get_document_tools()}
    assert "attachment:<file_id>" in DOCUMENT_TOOL_PROMPT


def test_the_prompt_points_at_the_listed_ids_and_keeps_the_tool_as_the_fallback() -> None:
    prompt = DOCUMENT_TOOL_PROMPT

    assert "list in this prompt" in prompt
    assert "list_attachments" in prompt and "missing" in prompt
    # The old rule made the tool call a precondition, which is what a small model skipped.
    assert "call list_attachments, then" not in prompt


def test_the_prompt_example_is_not_a_literal_the_model_can_paste_into_chat() -> None:
    """chat 8bb70bd4: the model copied `![alt text](attachment:...)` into its reply."""
    assert "![alt text](attachment:" not in DOCUMENT_TOOL_PROMPT
    assert "chat reply" in DOCUMENT_TOOL_PROMPT
