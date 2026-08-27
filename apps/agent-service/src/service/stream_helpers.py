"""Streaming infrastructure helpers extracted from api/routes/AgentsRoute.py.

These are pure SSE/async-iterator utilities with no route-level dependencies.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from langgraph.errors import GraphRecursionError


class Heartbeat:
    """Yielded by ``with_idle_heartbeat`` while the wrapped stream is quiet.

    Carries how long the current silence has lasted so the client can show
    the user that work is still happening rather than a frozen screen.
    """

    __slots__ = ("silent_seconds",)

    def __init__(self, silent_seconds: float) -> None:
        self.silent_seconds = silent_seconds


async def with_idle_heartbeat(
    source: Any,
    interval: float,
) -> Any:
    """Re-yield ``source``, injecting :class:`Heartbeat` during silent stretches.

    A model writing a document emits the whole body as tool-call arguments,
    and providers that only hand over the *completed* call (Ollama via
    langchain-ollama) send nothing at all while that happens — a long
    document can take minutes. ``DocumentProgressTracker`` cannot fill that
    gap for them because it has no argument chunks to count. Meanwhile any
    proxy in front of the stream sees an idle connection: Kong defaults to a
    60s read timeout and tears it down mid-generation, which surfaces in the
    browser as ``ERR_INCOMPLETE_CHUNKED_ENCODING``.
    """
    iterator = source.__aiter__()
    pending: asyncio.Future | None = None
    try:
        while True:
            pending = asyncio.ensure_future(iterator.__anext__())
            quiet_since = time.monotonic()
            while True:
                done, _ = await asyncio.wait({pending}, timeout=interval)
                if pending in done:
                    break
                yield Heartbeat(time.monotonic() - quiet_since)
            try:
                item = pending.result()
            except StopAsyncIteration:
                return
            finally:
                pending = None
            yield item
    finally:
        if pending is not None and not pending.done():
            pending.cancel()


def stream_error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout | httpx.ReadTimeout):
        return {
            "type": "error",
            "error": "LLM provider is unreachable. Check the provider URL, network, or model server status.",
            "content": "LLM provider is unreachable. Check the provider URL, network, or model server status.",
            "error_code": "provider_unavailable",
            "is_retryable": True,
            "details": {"exception_type": type(exc).__name__},
        }

    if isinstance(exc, GraphRecursionError):
        return {
            "type": "error",
            "error": "The agent took too many steps to finish this turn (too many searches/tool calls in a row) and was stopped.",
            "content": "The agent took too many steps to finish this turn (too many searches/tool calls in a row) and was stopped.",
            "error_code": "recursion_limit_exceeded",
            "is_retryable": True,
            "details": {"exception_type": type(exc).__name__},
        }

    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code if exc.response else None
        return {
            "type": "error",
            "error": "LLM provider returned an error.",
            "content": "LLM provider returned an error.",
            "error_code": "provider_http_error",
            "is_retryable": bool(status_code is None or status_code >= 500),
            "details": {
                "exception_type": type(exc).__name__,
                "status_code": status_code,
            },
        }

    return {
        "type": "error",
        "error": "Internal server error",
        "content": "Internal server error",
        "error_code": "internal_error",
        "is_retryable": True,
        "details": {"exception_type": type(exc).__name__},
    }
