import base64
import io
import logging
import re
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.messages import (
    ChatMessage as LangchainChatMessage,
)
from pypdf import PdfReader

from schema import ChatMessage

logger = logging.getLogger(__name__)

# Suppress pypdf warnings about uninterpretable fonts
logging.getLogger("pypdf").setLevel(logging.ERROR)


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


def is_garbage_text(text: str) -> bool:
    """
    Check if the extracted text looks like raw CID codes (garbage).
    Example garbage: /16/10 /6 /14 /7 /4 /12 /30 /i255
    """
    if not text or len(text) < 10:
        return False
    
    words = text.split()
    if not words:
        return False
        
    # Check ratio of words starting with / followed by digits or single chars
    # Heuristic: if > 30% of words look like CIDs (e.g. /12, /A, /i255)
    cid_matches = [w for w in words if re.match(r'^/[\w\d]+$', w)]
    
    if len(cid_matches) / len(words) > 0.3:
        return True
        
    return False


def extract_text_from_pdf(base64_data: str) -> str:
    try:
        pdf_bytes = base64.b64decode(base64_data)
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            
            # Check if extraction is empty or garbage (CID codes)
            # Retrying with layout mode might help for uninterpretable fonts or encodings
            if not text or len(text.strip()) < 5 or is_garbage_text(text):
                try:
                    # Try layout mode as fallback
                    text = page.extract_text(extraction_mode="layout")
                except Exception:
                    pass
            
            # If still garbage, return placeholder to avoid confusing LLM
            if is_garbage_text(text):
                text = "[Text extraction failed for this page: Unsupported PDF encoding]"
            
            # Ensure we don't append None
            if text:
                text_parts.append(text)
                
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"Failed to extract text from PDF: {e}")
        return "[Error extracting text from PDF]"


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
        role = msg.get("type", "human")
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
                    new_content.append({
                        "type": "text",
                        "text": f"--- Begin Content of {filename} ---\n{pdf_text}\n--- End Content of {filename} ---",
                    })
                    _maybe_store(metadata, data_b64, mime, filename)
                elif mime and not mime.startswith("image/"):
                    # Non-image file sent via "image" block — extract text
                    blocks = _extract_file_blocks(data_b64, mime, filename)
                    new_content.extend(blocks)
                    _maybe_store(metadata, data_b64, mime, filename)
                else:
                    # Actual image — convert to image_url block
                    new_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{data_b64}"},
                    })
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
        from service.FileService import get_file, store_file
        if get_file(file_id) is None:
            raw = base64.b64decode(data_b64)
            store_file(file_id, raw, mime, filename)
    except Exception as e:
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
            from service.FileService import FileRecord, _extract_text_from_record
            from datetime import UTC, datetime

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
            return [{"type": "image_url", "image_url": {"url": f"data:{m};base64,{data_b64}"}}]

        return [{
            "type": "text",
            "text": f"--- Begin Content of {filename} ---\n{text}\n--- End Content of {filename} ---",
        }]
    except Exception as e:
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
        content_item
        for content_item in content
        if isinstance(content_item, str) or content_item["type"] != "tool_use"
    ]
