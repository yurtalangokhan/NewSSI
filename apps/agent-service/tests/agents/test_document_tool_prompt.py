from agents.tooling.document_tools import (
    DOCUMENT_TOOL_PROMPT,
    _SHORT_DOCUMENT_DESCRIPTION,
    get_document_tools,
)


def test_prompt_states_the_edit_decision_rules() -> None:
    for phrase in (
        "edit_document",
        "rewrite_document",
        "read_document",
        "list_documents",
        "base_revision_no",
        "```mermaid",
        "never recreate",
    ):
        assert phrase in DOCUMENT_TOOL_PROMPT


def test_prompt_mentions_ambiguous_document_reference() -> None:
    assert "ambiguous" in DOCUMENT_TOOL_PROMPT
    assert "active" in DOCUMENT_TOOL_PROMPT


def test_prompt_keeps_download_url_preview_rule() -> None:
    assert "download_url" in DOCUMENT_TOOL_PROMPT
    assert "fails to preview" in DOCUMENT_TOOL_PROMPT


def test_short_document_description_mentions_options() -> None:
    assert "options" in _SHORT_DOCUMENT_DESCRIPTION


def test_every_document_tool_is_offered() -> None:
    names = {tool.name for tool in get_document_tools()}
    assert names == {
        "create_document",
        "create_spreadsheet",
        "list_documents",
        "list_attachments",
        "read_document",
        "edit_document",
        "rewrite_document",
    }
