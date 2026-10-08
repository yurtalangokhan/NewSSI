"""Translate external streaming failures into the public error contract."""

from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from error_contract import (
    ApplicationError,
    GraphExecutionLimitError,
    InternalServerError,
    from_httpx_error,
    render_error_message,
)
import httpx
from langgraph.errors import GraphRecursionError
from localization import get_locale

from core.http.response_models import ErrorModel, StreamEventModel
from core.observability.logger import get_logger

logger = get_logger(__name__)


def stream_error_event(exc: Exception, *, locale: str | None = None) -> StreamEventModel[dict[str, Any]]:
    """Keep the error code and localized message after HTTP headers are sent."""
    if isinstance(exc, ApplicationError):
        error = exc
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
    elif isinstance(exc, httpx.HTTPError):
        error = from_httpx_error(exc)
    elif isinstance(exc, GraphRecursionError):
        error = GraphExecutionLimitError()
    else:
        error = InternalServerError()
    message = render_error_message(error, locale=locale or get_locale())
    return StreamEventModel(
        event="error",
        data={
            "type": "error",
            "content": message,
            "error_code": error.code,
            "is_retryable": error.status_code >= 500 or isinstance(error, GraphExecutionLimitError),
        },
        error=ErrorModel.from_error(error, message),
    )


async def guard_stream(source: AsyncIterable[str | bytes]) -> AsyncIterator[str | bytes]:
    """Render failures in generator preparation and iteration after HTTP starts."""
    try:
        async for frame in source:
            yield frame
    except Exception as exc:
        logger.exception("Streaming response failed")
        yield stream_error_event(exc).to_sse()
