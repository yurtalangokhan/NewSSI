"""Pure helpers for extracting reasoning text from AI messages/chunks.

Extracted from ``service/agent_message_stream.py`` to reduce its LOC.  All
functions here are stateless.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessageChunk

from service.message_conversion import convert_message_content_to_string


def extract_reasoning_text(message: AIMessageChunk) -> str:
    """Extract provider-specific reasoning text from chunk metadata when available."""

    def _from_payload(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""

        # reasoning_delta carries per-token streaming chunks which may be
        # whitespace-only (e.g. "\n\n" between sections). Check presence only,
        # not strip(), so newlines and spaces are preserved.
        reasoning_delta = payload.get("reasoning_delta")
        if isinstance(reasoning_delta, str):
            return reasoning_delta

        for key in (
            "reasoning_content",  # Ollama (reasoning=True), DeepSeek API, OpenRouter
            "reasoning",  # Some OpenAI-compatible providers
            "thinking",  # Some providers
            "reasoning_text",  # Some providers
            "thoughts",  # Some providers
            "thought",  # Alternative key used by some providers
            "chain_of_thought",  # Some providers
        ):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, list):
                try:
                    return convert_message_content_to_string(value)
                except Exception:
                    continue

        nested = payload.get("content")
        if isinstance(nested, dict):
            return _from_payload(nested)

        return ""

    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
    response_metadata = getattr(message, "response_metadata", {}) or {}
    return _from_payload(additional_kwargs) or _from_payload(response_metadata)


def extract_reasoning_text_from_message(message: Any) -> str:
    """Extract reasoning text from final AI message metadata when chunks don't carry it."""

    def _from_payload(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""

        for key in (
            "reasoning_content",
            "reasoning",
            "thinking",
            "reasoning_text",
            "thoughts",
            "thought",
            "chain_of_thought",
        ):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, list):
                try:
                    text = convert_message_content_to_string(value)
                except Exception:
                    text = ""
                if text:
                    return text

        nested = payload.get("content")
        if isinstance(nested, dict):
            return _from_payload(nested)

        return ""

    def _from_content(content: Any) -> str:
        if isinstance(content, str):
            parts: list[str] = []
            for open_tag, close_tag in ((" thinking", " response"), ("<thinking>", "</thinking>")):
                start = 0
                while True:
                    open_pos = content.find(open_tag, start)
                    if open_pos == -1:
                        break
                    search_from = open_pos + len(open_tag)
                    close_pos = content.find(close_tag, search_from)
                    if close_pos == -1:
                        chunk = content[search_from:].strip()
                        if chunk:
                            parts.append(chunk)
                        break
                    chunk = content[search_from:close_pos].strip()
                    if chunk:
                        parts.append(chunk)
                    start = close_pos + len(close_tag)
            return "\n".join(parts).strip()

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type == "thinking":
                    text = str(item.get("thinking", "") or "").strip()
                    if text:
                        parts.append(text)
                elif item_type == "text" and item.get("thought"):
                    text = str(item.get("text", "") or "").strip()
                    if text:
                        parts.append(text)
            return "\n".join(parts).strip()

        return ""

    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
    response_metadata = getattr(message, "response_metadata", {}) or {}
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    return (
        _from_payload(additional_kwargs)
        or _from_payload(response_metadata)
        or _from_content(content)
    )
