"""Hardening of the document tool surface: argument recovery that never eats a
correct body, size limits on model-controlled arguments, per-tool retry hints,
fixed failure text, mid-loop fallback, and refusing an anonymous owner."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
import pytest

import agents.implementations.chatbot as chatbot_module
import agents.tooling.document_create_tools as create_tools
import agents.tooling.document_tool_support as support
import agents.tooling.document_tools as tools
from core.types.authored_documents import (
    MAX_DOCUMENT_CONTENT_CHARS,
    MAX_EDIT_SNIPPET_CHARS,
    MAX_EDITS_PER_CALL,
    MAX_REVISION_SUMMARY_CHARS,
)

DOC_ID = str(uuid4())
CONFIG = {"configurable": {"user_id": "u1", "thread_id": str(uuid4())}}


# ---------------------------------------------------------------------------
# 1. Content markup recovery never corrupts a correct body
# ---------------------------------------------------------------------------

_HTML_BODY = "# HTML\n\n```html\n<html>\n<body>\n<p>Merhaba</p>\n</body>\n</html>\n```\n\nSon.\n"


@pytest.mark.parametrize("args_extra", [{}, {"document_id": DOC_ID, "base_revision_no": 1}])
def test_fenced_html_body_is_left_untouched(args_extra) -> None:
    args = {"filename": "egitim", "format": "md", "content": _HTML_BODY, **args_extra}

    assert tools.recover_document_tool_args(args) == args


def test_explicit_content_is_not_stripped_of_surrounding_whitespace() -> None:
    args = {"filename": "a", "format": "txt", "content": "\n  girinti\n"}

    assert tools.recover_document_tool_args(args)["content"] == "\n  girinti\n"


def test_fully_wrapped_content_is_unwrapped_case_insensitively() -> None:
    recovered = tools.recover_document_tool_args(
        {"filename": "a", "format": "md", "content": "\n<Content>\n# Başlık\n</CONTENT>\n"}
    )

    assert recovered["content"] == "\n# Başlık\n"


def test_unpaired_leading_or_trailing_marker_is_removed() -> None:
    leading = tools.recover_document_tool_args({"filename": "a", "format": "md", "content": "<content># Başlık\n\nGövde"})
    trailing = tools.recover_document_tool_args({"filename": "a", "format": "md", "content": "# Başlık\n\nGövde</content>"})

    assert leading["content"] == "# Başlık\n\nGövde"
    assert trailing["content"] == "# Başlık\n\nGövde"


def test_tag_in_the_middle_of_content_is_kept() -> None:
    args = {"filename": "a", "format": "txt", "content": "önce <body> sonra </body> son"}

    assert tools.recover_document_tool_args(args) == args


def test_alias_body_keeps_tags_inside_fenced_code() -> None:
    recovered = tools.recover_document_tool_args({"filename": "a", "format": "md", "text": _HTML_BODY})

    assert recovered["content"] == _HTML_BODY.strip()


@pytest.mark.asyncio
async def test_html_body_survives_create_and_rewrite_through_the_chatbot_loop() -> None:
    seen: list[dict] = []

    class _Tool:
        async def ainvoke(self, args, config):
            seen.append(args)
            return "ok"

    create = {"name": "create_document", "args": {"filename": "a", "format": "md", "content": _HTML_BODY}}
    rewrite = {"name": "rewrite_document", "args": {"document_id": DOC_ID, "content": _HTML_BODY}}
    await chatbot_module._run_tool_call(_Tool(), create, {})
    await chatbot_module._run_tool_call(_Tool(), rewrite, {})

    assert [a["content"] for a in seen] == [_HTML_BODY, _HTML_BODY]


def test_edit_recovery_accepts_old_text_new_text_at_the_top_level() -> None:
    recovered = tools.recover_edit_tool_args({"old_text": "a", "new_text": "b"})

    assert recovered["edits"] == [{"old_str": "a", "new_str": "b"}]


# ---------------------------------------------------------------------------
# 2. Size limits surface as validation errors
# ---------------------------------------------------------------------------

_EDIT_BASE = {"document_id": DOC_ID, "base_revision_no": 1, "summary": "s"}


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        (
            tools.edit_document,
            {**_EDIT_BASE, "edits": [{"old_str": "x" * (MAX_EDIT_SNIPPET_CHARS + 1), "new_str": "y"}]},
        ),
        (
            tools.edit_document,
            {**_EDIT_BASE, "edits": [{"old_str": "x", "new_str": "y" * (MAX_EDIT_SNIPPET_CHARS + 1)}]},
        ),
        (
            tools.edit_document,
            {**_EDIT_BASE, "edits": [{"old_str": "x", "new_str": "y"}] * (MAX_EDITS_PER_CALL + 1)},
        ),
        (
            tools.edit_document,
            {**_EDIT_BASE, "summary": "s" * (MAX_REVISION_SUMMARY_CHARS + 1), "edits": [{"old_str": "x", "new_str": "y"}]},
        ),
        (
            tools.rewrite_document,
            {**_EDIT_BASE, "summary": "s" * (MAX_REVISION_SUMMARY_CHARS + 1), "content": "x"},
        ),
        (tools.rewrite_document, {**_EDIT_BASE, "content": "x" * (MAX_DOCUMENT_CONTENT_CHARS + 1)}),
        (
            tools.create_document,
            {"filename": "a", "format": "md", "content": "x" * (MAX_DOCUMENT_CONTENT_CHARS + 1)},
        ),
    ],
)
@pytest.mark.asyncio
async def test_oversized_arguments_are_rejected_as_a_tool_validation_error(tool, args) -> None:
    result = await chatbot_module._run_tool_call(tool, {"name": tool.name, "args": args}, CONFIG)

    assert result.startswith(f"Error: {tool.name} was not run")


# ---------------------------------------------------------------------------
# 3. Per-tool retry hints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "args", "expected", "unexpected"),
    [
        (tools.edit_document, {"document_id": DOC_ID}, "old_str", "belongs in `content`"),
        (tools.create_document, {"filename": "a", "format": "md"}, "`content`", None),
        (tools.create_spreadsheet, {"filename": "a", "format": "xlsx"}, "`sheets`", "belongs in `content`"),
        (tools.rewrite_document, {"document_id": DOC_ID}, "`content`", None),
        (tools.read_document, {}, "document_id", "belongs in `content`"),
    ],
)
@pytest.mark.asyncio
async def test_validation_error_hint_names_the_tools_own_arguments(tool, args, expected, unexpected) -> None:
    result = await chatbot_module._run_tool_call(tool, {"name": tool.name, "args": args}, CONFIG)

    assert result.startswith(f"Error: {tool.name} was not run")
    assert expected in result
    if unexpected:
        assert unexpected not in result


# ---------------------------------------------------------------------------
# 4. Fixed failure text and malformed spreadsheet rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unexpected_exception_text_never_reaches_the_model() -> None:
    class _Boom:
        async def ainvoke(self, args, config):
            raise RuntimeError("password=hunter2 at /srv/secret")

    result = await chatbot_module._run_tool_call(_Boom(), {"name": "create_document", "args": {}}, {})

    assert result == "Error: create_document failed unexpectedly; the error was logged."


@pytest.mark.asyncio
async def test_malformed_spreadsheet_rows_produce_the_invalid_content_message(monkeypatch) -> None:
    monkeypatch.setattr(support, "_emit_stream_event", lambda payload: None)

    class _Service:
        async def create(self, *args, **kwargs):
            from core.exceptions.authored_documents import InvalidDocumentContentError

            raise InvalidDocumentContentError("sheet rows must be a list")

    monkeypatch.setattr(support, "get_authored_document_service", lambda: _Service())

    result = await create_tools.create_spreadsheet.ainvoke(
        {"filename": "a", "format": "xlsx", "sheets": [{"name": "S", "rows": 5}]}, CONFIG
    )

    assert result.startswith("Error: invalid content")


# ---------------------------------------------------------------------------
# 5. Mid-loop fallback keeps committed tool results
# ---------------------------------------------------------------------------


class _MidLoopFailureModel:
    """Calls list_documents once, then the provider errors with a 'tool' message."""

    def __init__(self) -> None:
        self.bound_calls = 0
        self.plain_calls: list[list] = []

    def bind_tools(self, tools):
        bound = MagicMock()

        async def _ainvoke(messages):
            self.bound_calls += 1
            if self.bound_calls == 1:
                return AIMessage(content="", tool_calls=[{"name": "list_documents", "args": {}, "id": "c1"}])
            raise RuntimeError("503 upstream tool gateway timed out")

        bound.ainvoke = AsyncMock(side_effect=_ainvoke)
        return bound

    async def ainvoke(self, messages):
        self.plain_calls.append(list(messages))
        return AIMessage(content="Kapanış.")


@pytest.mark.asyncio
async def test_transient_error_after_a_tool_call_keeps_the_committed_messages(monkeypatch) -> None:
    model = _MidLoopFailureModel()
    monkeypatch.setattr(chatbot_module, "get_model_from_config", lambda configurable, default_model: model)
    monkeypatch.setattr(support, "get_authored_document_service", lambda: MagicMock())

    result = await chatbot_module.call_model(
        {"messages": [HumanMessage(content="Belgeleri listele")]},
        {"configurable": {"user_id": "u1"}},
        store=None,
    )

    kinds = [type(m).__name__ for m in result["messages"]]
    assert kinds == ["AIMessage", "ToolMessage", "AIMessage"]
    assert result["messages"][0].tool_calls[0]["id"] == "c1"
    assert result["messages"][-1].content == "Kapanış."


class _FirstCallErrorModel:
    def __init__(self, error: str) -> None:
        self.error = error
        self.plain_calls = 0

    def bind_tools(self, tools):
        bound = MagicMock()
        bound.ainvoke = AsyncMock(side_effect=RuntimeError(self.error))
        return bound

    async def ainvoke(self, messages):
        self.plain_calls += 1
        return AIMessage(content="düz")


@pytest.mark.asyncio
async def test_unrelated_first_call_error_is_not_swallowed_as_missing_tool_support(monkeypatch) -> None:
    model = _FirstCallErrorModel("connection reset while streaming tokens to the tool endpoint")
    monkeypatch.setattr(chatbot_module, "get_model_from_config", lambda configurable, default_model: model)

    with pytest.raises(RuntimeError):
        await chatbot_module.call_model(
            {"messages": [HumanMessage(content="Merhaba")]}, {"configurable": {"user_id": "u1"}}, store=None
        )

    assert model.plain_calls == 0


def test_the_exhausted_loop_fallback_text_is_localized_and_not_creation_specific() -> None:
    from localization import t

    text = t("agent.tool_loop_incomplete")

    assert text != "agent.tool_loop_incomplete"
    assert "creating" not in text


# ---------------------------------------------------------------------------
# 6. A missing user is refused, never shared
# ---------------------------------------------------------------------------


def test_actor_from_config_refuses_a_missing_user() -> None:
    with pytest.raises(support.MissingUserError):
        support.actor_from_config({"configurable": {}})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "args"),
    [
        (tools.list_documents, {}),
        (tools.read_document, {"document_id": DOC_ID}),
        (tools.edit_document, {**_EDIT_BASE, "edits": [{"old_str": "a", "new_str": "b"}]}),
        (tools.rewrite_document, {**_EDIT_BASE, "content": "x"}),
        (tools.create_document, {"filename": "a", "format": "md", "content": "x"}),
    ],
)
async def test_tools_refuse_a_call_without_a_user(monkeypatch, tool, args) -> None:
    monkeypatch.setattr(support, "_emit_stream_event", lambda payload: None)
    monkeypatch.setattr(support, "get_authored_document_service", lambda: MagicMock())

    result = await tool.ainvoke(args, {"configurable": {}})

    assert result.startswith(f"Error: {tool.name} needs an authenticated user")


# ---------------------------------------------------------------------------
# 7. Prompt and docstring wording
# ---------------------------------------------------------------------------


def test_prompt_states_that_rewrite_replaces_sheet_content() -> None:
    assert "the sheet content is preserved" not in tools.DOCUMENT_TOOL_PROMPT
    assert "edit_document" in tools.DOCUMENT_TOOL_PROMPT and "csv" in tools.DOCUMENT_TOOL_PROMPT


def test_create_tools_do_not_promise_a_short_confirmation() -> None:
    assert "short confirmation" not in (tools.create_document.description or "")
    assert "short confirmation" not in (tools.create_spreadsheet.description or "")


# ---------------------------------------------------------------------------
# 8. options typing is aligned
# ---------------------------------------------------------------------------


def test_edit_recovery_decodes_a_string_options_object() -> None:
    recovered = tools.recover_edit_tool_args(
        {"edits": [{"old_str": "a", "new_str": "b"}], "options": json.dumps({"toc": None})}
    )

    assert recovered["options"] == {"toc": None}
