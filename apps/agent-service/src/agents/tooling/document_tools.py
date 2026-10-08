"""
Document output tools — always-available LangChain tools that let any agent
(including the default chatbot persona, regardless of the underlying model)
produce a downloadable PDF / DOCX / XLSX / CSV / MD / TXT file during a chat,
look at the drafts it already produced, and revise them.

Unlike MCP tools, these are not opt-in per agent: `get_document_tools()` is
injected into every graph build unless disabled via
`env.DOCUMENT_TOOLS_ENABLED`.

This module is the public face of the tool set: the system prompt, the tool
list and binding. The tools themselves live in focused modules —
``document_create_tools`` (create), ``document_workspace_tools`` (list/read),
``document_edit_tools`` (edit/rewrite) — over the shared plumbing in
``document_tool_support`` and the argument repair in ``document_tool_args``.
"""

from __future__ import annotations

from typing import Any

from config_manager import env
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool

from agents.tooling.document_create_tools import create_document, create_spreadsheet
from agents.tooling.document_edit_tools import edit_document, rewrite_document
from agents.tooling.document_tool_args import recover_document_tool_args, recover_edit_tool_args
from agents.tooling.document_tool_messages import describe_error
from agents.tooling.document_tool_support import StreamProgressSink, actor_from_config, revision_payload
from agents.tooling.document_workspace_tools import list_attachments, list_documents, read_document
from core.observability.logger import get_logger

logger = get_logger(__name__)

__all__ = [
    "DOCUMENT_TOOL_PROMPT",
    "StreamProgressSink",
    "actor_from_config",
    "bind_document_tools",
    "create_document",
    "create_spreadsheet",
    "describe_error",
    "edit_document",
    "get_document_tools",
    "list_attachments",
    "list_documents",
    "read_document",
    "recover_document_tool_args",
    "recover_edit_tool_args",
    "revision_payload",
    "rewrite_document",
]

DOCUMENT_TOOL_PROMPT = (
    "Documents:\n"
    "- Documents you create are living drafts. Each change you make creates a new "
    "draft (the user can browse, compare and restore drafts), so never recreate a "
    "document just to change it.\n"
    "- Choose the tool:\n"
    "  • New deliverable the user asked for → create_document / create_spreadsheet.\n"
    "  • Change to a document that already exists in this conversation (fix, add, "
    "remove, reword, restyle, update a diagram) → edit_document.\n"
    "  • Changes that touch most of the text (translate, restructure, change tone "
    "everywhere) → rewrite_document.\n"
    "  • Format change among pdf/docx/md/txt → edit_document or rewrite_document "
    "with the new format.\n"
    "  • Convert between xlsx and csv with `format` on edit_document: the sheets "
    "are kept and only the rendered file changes. rewrite_document replaces the "
    "sheets with the `content` you pass, so use it only with the complete sheets "
    "array.\n"
    "  • Format change to or from json → rewrite_document with the content written "
    "in the new format (JSON when going to json, Markdown when leaving it); "
    "edit_document cannot do this because the whole content must be replaced.\n"
    "  • Format change between a document (pdf/docx/md/txt/json) and a spreadsheet "
    "(xlsx/csv) is impossible — tell the user.\n"
    "  • Only if the user explicitly wants a separate/new file → create a new "
    "document.\n"
    "- Before editing, make sure you know the current text: if the exact current "
    "content is not already in this conversation (for example the user edited it, "
    "or it was created long ago), call read_document first — old_str must always "
    "come from the latest draft. Use list_documents when you are unsure which "
    'document the user means, including when the user refers to "the document" '
    "ambiguously; the entry marked active is the one open in the user's panel.\n"
    "- edit_document rules: copy old_str verbatim from the latest draft, "
    "including spaces, punctuation and table pipes; include enough surrounding "
    "text to make it unique; one edit per distinct change; to insert, anchor on "
    "nearby text and repeat it in new_str; to delete, set old_str to the anchor "
    "plus the removed part and new_str to the anchor alone. Always pass "
    "base_revision_no from the latest tool result. If a call fails, read the "
    "error, re-read the document if told to, and retry once with corrected "
    "edits — never fall back to creating a new file.\n"
    "- Diagrams: write Mermaid in ```mermaid fenced blocks (flowchart, "
    "sequenceDiagram, classDiagram, stateDiagram-v2, erDiagram, gantt, pie, "
    "mindmap, timeline). Wrap node labels that contain punctuation in double "
    'quotes, e.g. A["Step (1)"]; avoid bare `end`, `;` and unbalanced brackets '
    "in labels. If a tool reports a diagram error, fix that block and retry "
    "once.\n"
    "- Images the user attached to the chat can be embedded in pdf/docx documents: "
    "take a file_id from the attached-images list in this prompt (call "
    "list_attachments only when that list is missing or you are unsure), and put "
    "![<describe the image>](attachment:<file_id>) on its own line in the content "
    "you pass to create_document / edit_document / rewrite_document. It only works "
    "there: a chat reply cannot show it, so never write it in your answer. Only "
    "listed file_ids work; never invent one or use a URL or data: URI for an "
    "attachment.\n"
    "- In chat replies you may also show Mermaid diagrams directly in a "
    "```mermaid block when a picture explains better than text.\n"
    "- After a document tool succeeds, reply with one or two sentences on what "
    "changed. Do not paste the document. Do NOT include the `download_url` from "
    "the tool result (or any other link to the file) in your reply — the UI "
    "already renders a clickable download card for it, and a second link in "
    "your text opens without knowing the file's real type, so it fails to "
    "preview.\n"
    "- Do not create or edit documents for greetings, small talk or questions "
    "that only need a chat answer."
)

_SHORT_DOCUMENT_DESCRIPTION = (
    "Create a downloadable document (PDF, DOCX, Markdown, plain text, or "
    "JSON) from Markdown content (or a JSON string for the json format). "
    "Requires filename, format, content. Optional: title, "
    "options (theme/page/header/footer/cover/toc/numbering/tables/watermark — "
    "omit for a sensibly-themed default)."
)
_SHORT_SPREADSHEET_DESCRIPTION = (
    "Create a downloadable spreadsheet (XLSX or CSV) from tabular data. "
    "Requires filename, format, sheets. Optional: options (theme, header "
    "styling, column widths/formats/alignments, conditional formatting)."
)

_SHORT_LIST_DESCRIPTION = (
    "List this conversation's documents: the active document first, then newest first "
    "(the one the user has open is marked active)."
)
_SHORT_ATTACHMENTS_DESCRIPTION = (
    "List images the user attached to this conversation; embed one in a document with "
    "![alt](attachment:<file_id>) on its own line."
)
_SHORT_READ_DESCRIPTION = (
    "Read a document draft's text with an outline. Lines are prefixed `NNNN | ` for orientation only; "
    "never copy the prefix into old_str."
)
_SHORT_EDIT_DESCRIPTION = (
    "Change an existing document with exact find-and-replace edits (old_str copied verbatim from the "
    "latest draft — call read_document first when it isn't already in the conversation — unique; one "
    "edit per change) against the latest base_revision_no; saves the next draft. Never create a new "
    "file instead. options is a partial patch; null resets a key."
)
_SHORT_REWRITE_DESCRIPTION = (
    "Replace an existing document's whole body (Markdown; JSON string for json; the JSON sheets array for "
    "a spreadsheet) against the latest base_revision_no; saves the next draft. Prefer edit_document for "
    "local changes."
)


def get_document_tools() -> list[BaseTool]:
    """Return the always-on document tools, or [] if disabled via env.

    The `options` reference costs ~350 tokens per request; when
    `DOCUMENT_TOOLS_RICH_OPTIONS` is off, token-sensitive or small
    local-model setups get a short description instead — `options` still
    works, the model just isn't told about it in detail.
    """
    if not env.DOCUMENT_TOOLS_ENABLED:
        return []
    if env.DOCUMENT_TOOLS_RICH_OPTIONS:
        return [
            create_document,
            create_spreadsheet,
            list_documents,
            list_attachments,
            read_document,
            edit_document,
            rewrite_document,
        ]
    return [
        create_document.model_copy(update={"description": _SHORT_DOCUMENT_DESCRIPTION}),
        create_spreadsheet.model_copy(update={"description": _SHORT_SPREADSHEET_DESCRIPTION}),
        list_documents.model_copy(update={"description": _SHORT_LIST_DESCRIPTION}),
        list_attachments.model_copy(update={"description": _SHORT_ATTACHMENTS_DESCRIPTION}),
        read_document.model_copy(update={"description": _SHORT_READ_DESCRIPTION}),
        edit_document.model_copy(update={"description": _SHORT_EDIT_DESCRIPTION}),
        rewrite_document.model_copy(update={"description": _SHORT_REWRITE_DESCRIPTION}),
    ]


def bind_document_tools(model: BaseChatModel, tools: list[BaseTool]) -> tuple[Any, bool]:
    """Bind tools to a model, falling back gracefully if tool-calling is unsupported.

    Returns (possibly-bound model, whether binding succeeded). Callers should
    only wire up a tool-execution loop when the second element is True.
    """
    try:
        return model.bind_tools(tools), True
    except Exception as exc:
        logger.warning("Model does not support tool binding, disabling tools: %s", exc)
        return model, False
