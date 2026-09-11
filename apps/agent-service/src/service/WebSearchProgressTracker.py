"""Translates web_search / fetch_webpage tool activity into the same
search_tool_* / open_url_* SSE packets the internal-search and
document-open frontend renderers already consume, instead of the generic
custom_tool_* packets every other tool falls through to (see
DocumentProgressTracker for that same custom-tool special-casing pattern
applied to create_document/create_spreadsheet).

Unlike DocumentProgressTracker, tool-call arguments here are tiny (a query
string or a URL) and always arrive whole rather than streamed
char-by-char, so no incremental buffering is needed — one call in, one
packet list out. The only state this tracker keeps is call_id -> url, so a
fetch_webpage result (whose tool content has no URL in it) can be matched
back to the URL its own tool call requested.
"""

from __future__ import annotations

import json
import re
from typing import Any

WEB_SEARCH_TOOL_NAME = "web_search"
FETCH_WEBPAGE_TOOL_NAME = "fetch_webpage"

# Matches one "TITLE: ...\nURL: ...\nSNIPPET: ..." block from
# format_web_search_results (tools-service), blocks separated by "\n---\n".
_WEB_SEARCH_RESULT_RE = re.compile(
    r"TITLE:\s*(?P<title>.*?)\s*\n"
    r"URL:\s*(?P<url>.*?)\s*\n"
    r"SNIPPET:\s*(?P<snippet>.*?)\s*(?=\n---|\Z)",
    re.DOTALL,
)

# Matches the "TITLE: ...\n[DESCRIPTION: ...\n]---\n<body>" header
# fetch_webpage_content (tools-service) prefixes onto a successful fetch.
_FETCH_TITLE_RE = re.compile(r"\ATITLE:\s*(?P<title>.*?)\s*\n")
_FETCH_DESCRIPTION_RE = re.compile(r"\nDESCRIPTION:\s*(?P<description>.*?)\s*\n")
_FETCH_BODY_RE = re.compile(r"\n---\n(?P<body>.*)\Z", re.DOTALL)

_BLURB_FALLBACK_LENGTH = 300


def is_web_search_tool(tool_name: str | None) -> bool:
    """True when `tool_name` is one of the two web tools this tracker
    translates into search_tool_*/open_url_* packets."""
    return tool_name in (WEB_SEARCH_TOOL_NAME, FETCH_WEBPAGE_TOOL_NAME)


def _coerce_args(args: Any) -> dict[str, Any]:
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (ValueError, TypeError):
            return {}
    return args if isinstance(args, dict) else {}


def _base_document(
    url: str,
    title: str,
    blurb: str,
    is_error: bool = False,
    error: str | None = None,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "document_id": url,
        "semantic_identifier": title or url,
        "link": url,
        "source_type": "web",
        "blurb": blurb,
        "boost": 0,
        "hidden": False,
        "score": 1.0,
        "chunk_ind": 0,
        "match_highlights": [],
        "metadata": {"error": error} if error else {},
        "updated_at": None,
        "is_internet": True,
    }
    if is_error:
        doc["is_error"] = True
        doc["error"] = error or blurb
        doc["validationState"] = "bad"
    return doc


class WebSearchProgressTracker:
    """One tracker instance per stream (or per history-reconstruction
    branch — see `clone()`). Remembers which URL each in-flight
    `fetch_webpage` call_id requested, since the tool's result text has no
    URL in it."""

    def __init__(self) -> None:
        self._fetch_urls_by_call_id: dict[str, str] = {}

    def on_tool_call(
        self, tool_name: str, args: Any, call_id: str | None
    ) -> list[dict[str, Any]] | None:
        if tool_name == WEB_SEARCH_TOOL_NAME:
            query = _coerce_args(args).get("query") or ""
            return [
                {"type": "search_tool_start", "is_internet_search": True, "call_id": call_id},
                {
                    "type": "search_tool_queries_delta",
                    "queries": [query] if query else [],
                    "call_id": call_id,
                },
            ]

        if tool_name == FETCH_WEBPAGE_TOOL_NAME:
            url = _coerce_args(args).get("url") or ""
            if call_id and url:
                self._fetch_urls_by_call_id[call_id] = url
            packet_call_id = call_id or url
            return [
                {"type": "open_url_start", "call_id": packet_call_id},
                {"type": "open_url_urls", "urls": [url] if url else [], "call_id": packet_call_id},
            ]

        return None

    def on_tool_result(
        self, tool_name: str, content: Any, call_id: str | None
    ) -> list[dict[str, Any]] | None:
        if not isinstance(content, str):
            return None

        if tool_name == WEB_SEARCH_TOOL_NAME:
            documents = [
                _base_document(
                    m.group("url").strip(), m.group("title").strip(), m.group("snippet").strip()
                )
                for m in _WEB_SEARCH_RESULT_RE.finditer(content)
                if m.group("url").strip()
            ]
            return [
                {"type": "search_tool_documents_delta", "documents": documents, "call_id": call_id}
            ]

        if tool_name == FETCH_WEBPAGE_TOOL_NAME:
            url = self._fetch_urls_by_call_id.pop(call_id, "") if call_id else ""
            packet_call_id = call_id or url
            title_match = _FETCH_TITLE_RE.search(content)
            if not title_match:
                # Page could not be fetched or returned an error (e.g. 404, 500, timeout).
                # Emitting an open_url_documents packet with the URL and error blurb completes
                # the fetch step gracefully without falling back to a generic custom_tool_delta.
                if url:
                    doc = _base_document(
                        url=url,
                        title=url,
                        blurb=content.strip()[:_BLURB_FALLBACK_LENGTH],
                        is_error=True,
                        error=content.strip()[:_BLURB_FALLBACK_LENGTH],
                    )
                    return [
                        {
                            "type": "open_url_documents",
                            "documents": [doc],
                            "call_id": packet_call_id,
                        }
                    ]
                return [{"type": "open_url_documents", "documents": [], "call_id": packet_call_id}]

            description_match = _FETCH_DESCRIPTION_RE.search(content)
            if description_match:
                blurb = description_match.group("description").strip()
            else:
                body_match = _FETCH_BODY_RE.search(content)
                blurb = (
                    body_match.group("body").strip()[:_BLURB_FALLBACK_LENGTH] if body_match else ""
                )

            doc_title = title_match.group("title").strip()
            return [
                {
                    "type": "open_url_documents",
                    "documents": [_base_document(url or doc_title, doc_title, blurb)],
                    "call_id": packet_call_id,
                }
            ]

        return None

    def clone(self) -> WebSearchProgressTracker:
        cloned = WebSearchProgressTracker()
        cloned._fetch_urls_by_call_id = dict(self._fetch_urls_by_call_id)
        return cloned


def replay_packets_for_call(
    tool_name: str, args: Any, call_id: str | None, result: str
) -> list[dict[str, Any]] | None:
    """The exact search_tool_* / open_url_* packet run a live stream emitted
    for one web tool call, rebuilt from that call's args and raw result.

    Used at write time to store a replayable copy on the flow timeline blob,
    and at read time to recover the widget for runs recorded before that blob
    kept one. Returns None for tools this tracker does not translate.
    """
    tracker = WebSearchProgressTracker()
    start = tracker.on_tool_call(tool_name, args, call_id)
    if start is None:
        return None
    return [*start, *(tracker.on_tool_result(tool_name, result, call_id) or [])]
