import base64
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ChatMessage as LangchainChatMessage,
    HumanMessage,
    ToolMessage,
)

from core.observability.logger import get_logger
from core.utils.pdf_utils import extract_text_from_pdf
from schemas.chat import ChatMessage

logger = get_logger(__name__)

# Suppress pypdf warnings about uninterpretable fonts
get_logger("pypdf").setLevel("ERROR")


def convert_message_content_to_string(content: str | list[str | dict]) -> str:
    if isinstance(content, str):
        return content
    text: list[str] = []
    for content_item in content:
        if isinstance(content_item, str):
            text.append(content_item)
            continue
        if content_item["type"] == "text":
            text.append(content_item["text"])
    return "".join(text)


def extract_reasoning_from_metadata(msg: Any, *, strip: bool = True) -> str:
    """Pull reasoning/"thinking" text out of a message's provider-specific
    metadata (``additional_kwargs``/``response_metadata``), where models
    like reasoning-capable Ollama/DeepSeek variants attach it separately
    from the visible ``content``. Shared between the main chat stream
    (chat_management_service.py) and the flow playground stream (RunService.py) so
    both surface a live "Thinking…" block the same way.

    ``strip=False`` for RunService's per-chunk streaming use: each chunk is
    a fragment of a longer reasoning text, so trimming its edges would glue
    words together once consecutive deltas are concatenated by the client
    (e.g. "Let" + strip(" me") -> "Letme"). The default (whole, already-
    complete message) keeps trimming outer whitespace.
    """

    def _stringify(value: Any) -> str:
        if isinstance(value, str):
            return value.strip() if strip else value
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str) and item:
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("reasoning") or item.get("thinking")
                    if isinstance(text, str) and text:
                        parts.append(text)
            joined = "\n".join(parts)
            return joined.strip() if strip else joined
        return ""

    def _pick(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""

        reasoning_delta = payload.get("reasoning_delta")
        if isinstance(reasoning_delta, str):
            return reasoning_delta

        for key in (
            "reasoning_content",
            "reasoning",
            "thinking",
            "reasoning_text",
            "thoughts",
            "thought",
            "chain_of_thought",
        ):
            extracted = _stringify(payload.get(key))
            if extracted:
                return extracted

        nested_content = payload.get("content")
        if isinstance(nested_content, dict):
            return _pick(nested_content)

        return ""

    if isinstance(msg, dict):
        additional_kwargs = msg.get("additional_kwargs", {}) or {}
        response_metadata = msg.get("response_metadata", {}) or {}
    else:
        additional_kwargs = getattr(msg, "additional_kwargs", {}) or {}
        response_metadata = getattr(msg, "response_metadata", {}) or {}

    return _pick(additional_kwargs) or _pick(response_metadata)


def split_message_content_reasoning(content: Any) -> tuple[str, str]:
    """Split a message/chunk ``content`` into ``(reasoning_text, visible_text)``.

    Providers like Anthropic (extended thinking) and Google Gemini (thought
    summaries) return reasoning inline in the content block list rather than in
    ``additional_kwargs``:

    - ``{"type": "thinking", "thinking": "..."}``            -> reasoning
    - ``{"type": "reasoning", "reasoning"/"text": "..."}``    -> reasoning
    - ``{"type": "text", "thought": true, "text": "..."}``    -> reasoning
    - ``{"type": "text", "text": "..."}``                     -> visible

    A plain string is treated entirely as visible text. Parts are concatenated
    with no separator so consecutive streaming deltas join cleanly.
    """
    if isinstance(content, str):
        return "", content
    if not isinstance(content, list):
        return "", ""

    reasoning_parts: list[str] = []
    visible_parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            if item:
                visible_parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "thinking":
            text = item.get("thinking")
            if isinstance(text, str) and text:
                reasoning_parts.append(text)
        elif item_type == "reasoning":
            text = item.get("reasoning") or item.get("text")
            if isinstance(text, str) and text:
                reasoning_parts.append(text)
        elif item_type == "text":
            text = item.get("text")
            if not isinstance(text, str) or not text:
                continue
            if item.get("thought"):
                reasoning_parts.append(text)
            else:
                visible_parts.append(text)

    return "".join(reasoning_parts), "".join(visible_parts)


def convert_input_messages(messages: list[dict[str, Any]]) -> list[BaseMessage]:
    """Convert raw input messages to LangChain BaseMessage objects.

    Supports inline base64 content blocks (legacy / LangChain SDK format):
      - {type: "image", mime_type, data, metadata: {name, file_id?}}
      - {type: "file",  mime_type, data, metadata: {filename, file_id?}}

    For file types, text is extracted using FileService parsers and injected
    as text blocks.  Image files become image_url blocks for multimodal LLMs.

    When a file_id is present in metadata, the raw bytes are also stored in
    FileService._STORE so GET /api/chat/file/{id} can serve them later
    (needed for CsvContent table rendering).
    """
    langchain_messages = []
    for msg in messages:
        content = msg.get("content", [])

        if isinstance(content, str):
            langchain_messages.append(HumanMessage(content=content))
            continue

        new_content = []
        for item in content:
            if isinstance(item, str):
                new_content.append({"type": "text", "text": item})
                continue

            item_type = item.get("type")
            if item_type == "text":
                new_content.append(item)

            elif item_type == "image":
                mime = item.get("mime_type", "")
                data_b64 = item.get("data", "")
                metadata = item.get("metadata", {})
                filename = metadata.get("filename") or metadata.get("name") or "image"

                if mime == "application/pdf":
                    # PDF sent as "image" block (legacy frontend SDK workaround)
                    pdf_text = extract_text_from_pdf(data_b64)
                    new_content.append(
                        {
                            "type": "text",
                            "text": f"--- Begin Content of {filename} ---\n{pdf_text}\n--- End Content of {filename} ---",
                        }
                    )
                    _maybe_store(metadata, data_b64, mime, filename)
                elif mime and not mime.startswith("image/"):
                    # Non-image file sent via "image" block — extract text
                    blocks = _extract_file_blocks(data_b64, mime, filename)
                    new_content.extend(blocks)
                    _maybe_store(metadata, data_b64, mime, filename)
                else:
                    # Actual image — convert to image_url block
                    from service.storage.file_service import normalize_image_for_llm

                    norm_data, norm_mime = normalize_image_for_llm(data_b64, mime or "image/jpeg")
                    new_content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{norm_mime};base64,{norm_data}"},
                        }
                    )
                    _maybe_store(metadata, data_b64, mime, filename)

            elif item_type == "file":
                mime = item.get("mime_type", "application/octet-stream")
                data_b64 = item.get("data", "")
                metadata = item.get("metadata", {})
                filename = metadata.get("filename") or metadata.get("name") or "file"

                blocks = _extract_file_blocks(data_b64, mime, filename)
                new_content.extend(blocks)
                _maybe_store(metadata, data_b64, mime, filename)

            else:
                logger.warning("Unknown content type in message: %s", item_type)

        langchain_messages.append(HumanMessage(content=new_content))

    return langchain_messages


# ---------------------------------------------------------------------------
# Helpers for convert_input_messages
# ---------------------------------------------------------------------------


def _maybe_store(metadata: dict, data_b64: str, mime: str, filename: str) -> None:
    """Store file bytes in FileService._STORE if a file_id is present in metadata."""
    file_id = metadata.get("file_id")
    if not file_id or not data_b64:
        return
    try:
        from service.storage.file_service import get_file, store_file

        if get_file(file_id) is None:
            raw = base64.b64decode(data_b64)
            store_file(file_id, raw, mime, filename)
    except (ValueError, TypeError) as e:
        logger.debug("Could not store file %s in _STORE: %s", file_id, e)


def _extract_file_blocks(data_b64: str, mime: str, filename: str) -> list[dict]:
    """Extract text from a base64-encoded file and return LangChain content blocks."""
    if not data_b64:
        return []

    m = mime.lower().split(";")[0].strip()

    try:
        if m == "application/pdf":
            text = extract_text_from_pdf(data_b64)
        else:
            raw = base64.b64decode(data_b64)
            from datetime import UTC, datetime

            from service.storage.file_service import FileRecord, _extract_text_from_record

            # Build a temporary record for the extraction machinery
            tmp = FileRecord(
                file_id="_tmp_",
                data=raw,
                mime_type=m,
                filename=filename,
                chat_file_type="document",
                created_at=datetime.now(UTC),
            )
            text = _extract_text_from_record(tmp)

        if text is None:
            # Image that slipped through — convert to image_url
            from service.storage.file_service import normalize_image_for_llm

            norm_data, norm_mime = normalize_image_for_llm(data_b64, m or "image/jpeg")
            return [{"type": "image_url", "image_url": {"url": f"data:{norm_mime};base64,{norm_data}"}}]

        return [
            {
                "type": "text",
                "text": f"--- Begin Content of {filename} ---\n{text}\n--- End Content of {filename} ---",
            }
        ]
    except (ValueError, TypeError, OSError) as e:
        logger.error("Failed to extract content from %s (%s): %s", filename, mime, e)
        return [{"type": "text", "text": f"[Could not extract content from {filename}]"}]


def langchain_to_chat_message(message: BaseMessage) -> ChatMessage:
    """Create a ChatMessage from a LangChain message."""
    match message:
        case HumanMessage():
            human_message = ChatMessage(
                type="human",
                content=convert_message_content_to_string(message.content),
            )
            return human_message
        case AIMessage():
            ai_message = ChatMessage(
                type="ai",
                content=convert_message_content_to_string(message.content),
            )
            if message.tool_calls:
                ai_message.tool_calls = message.tool_calls
            if message.response_metadata:
                ai_message.response_metadata = message.response_metadata
            return ai_message
        case ToolMessage():
            tool_message = ChatMessage(
                type="tool",
                content=convert_message_content_to_string(message.content),
                tool_call_id=message.tool_call_id,
            )
            return tool_message
        case LangchainChatMessage():
            if message.role == "custom":
                custom_message = ChatMessage(
                    type="custom",
                    content="",
                    custom_data=message.content[0],
                )
                return custom_message
            else:
                raise ValueError(f"Unsupported chat message role: {message.role}")
        case _:
            raise ValueError(f"Unsupported message type: {message.__class__.__name__}")


def remove_tool_calls(content: str | list[str | dict]) -> str | list[str | dict]:
    """Remove tool calls from content."""
    if isinstance(content, str):
        return content
    # Currently only Anthropic models stream tool calls, using content item type tool_use.
    return [
        content_item for content_item in content if isinstance(content_item, str) or content_item["type"] != "tool_use"
    ]
