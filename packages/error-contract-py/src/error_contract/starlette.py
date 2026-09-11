import logging

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

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

        async def call_next(_: Request) -> Response:
            await self.app(scope, receive, send)
            return Response(status_code=204)

        try:
            await call_next(request)
        except Exception:
            logger.error(
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
                    "request_id": request.headers.get("x-request-id")
                    or request.headers.get("x-correlation-id"),
                },
            )
            response = _safe_response(request)
            await response(scope, receive, send)


def _safe_response(request: Request) -> JSONResponse:
    envelope = ErrorEnvelope.from_error(
        code="internal.server_error",
        message="An unexpected error occurred.",
        request_id=request.headers.get("x-request-id")
        or request.headers.get("x-correlation-id"),
    )
    return JSONResponse(status_code=500, content=envelope.model_dump())
