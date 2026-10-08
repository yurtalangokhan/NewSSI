import logging

from localization import normalize_locale
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from ._request_id import resolve_request_id
from .exceptions import ApplicationError, InternalServerError
from .localization import render_error_message
from .models import ErrorEnvelope

logger = logging.getLogger(__name__)


class ErrorContractMiddleware:
    """Starlette/FastMCP-compatible fallback error envelope middleware."""

    def __init__(self, app: ASGIApp, *, service_name: str) -> None:
        self.app = app
        self.service_name = service_name

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        request_id = resolve_request_id(request.headers)
        locale = _request_locale(request)
        response_started = False

        async def send_with_state(message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_with_state)
        except ApplicationError as exc:
            if response_started:
                logger.error(
                    "Unhandled %s request failed after response start: %s %s -> %s",
                    self.service_name,
                    request.method,
                    request.url.path,
                    exc.code,
                )
                raise
            response = _error_response(request_id, exc, locale=locale)
            await response(scope, receive, send_with_state)
        except Exception:
            logger.exception(
                "Unhandled %s request failed: %s %s -> internal.server_error",
                self.service_name,
                request.method,
                request.url.path,
                extra={
                    "event": "http.request.unhandled_error",
                    "service": self.service_name,
                    "method": request.method,
                    "path": request.url.path,
                    "error_code": "internal.server_error",
                    "safe_message": "An unexpected error occurred.",
                    "request_id": request_id,
                },
            )
            if response_started:
                raise
            response = _error_response(request_id, InternalServerError(), locale=locale)
            await response(scope, receive, send_with_state)


def _error_response(
    request_id: str,
    error: ApplicationError,
    *,
    locale: str,
) -> JSONResponse:
    envelope = ErrorEnvelope.from_error(
        code=error.code,
        message=render_error_message(error, locale=locale),
        details=error.details,
        field_errors=error.field_errors,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=error.status_code,
        content=envelope.model_dump(),
        headers={**error.headers, "Content-Language": locale, "X-Request-ID": request_id},
    )


def _request_locale(request: Request) -> str:
    state_locale = getattr(request.state, "locale", None)
    if state_locale:
        return normalize_locale(str(state_locale))
    requested = (
        request.query_params.get("lang")
        or request.query_params.get("locale")
        or request.headers.get("x-language")
        or request.headers.get("accept-language")
        or "en"
    )
    return normalize_locale(requested)
