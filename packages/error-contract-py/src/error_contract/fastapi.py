import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .exceptions import ApplicationError
from .models import ErrorEnvelope, FieldError

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI, *, service_name: str) -> None:
    """Register platform-standard error handlers on a FastAPI app."""

    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
        return _json_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            field_errors=exc.field_errors,
            request_id=_request_id(request),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        code, message, details = _from_http_detail(exc.status_code, exc.detail)
        return _json_response(
            status_code=exc.status_code,
            code=code,
            message=message,
            details=details,
            request_id=_request_id(request),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _json_response(
            status_code=422,
            code="validation.failed",
            message="Request validation failed.",
            field_errors=_validation_field_errors(exc),
            request_id=_request_id(request),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled %s error for %s %s",
            service_name,
            request.method,
            request.url.path,
            exc_info=exc,
        )
        return _json_response(
            status_code=500,
            code="internal.server_error",
            message="An unexpected error occurred.",
            request_id=_request_id(request),
        )


def _json_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    field_errors: list[FieldError] | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    envelope = ErrorEnvelope.from_error(
        code=code,
        message=message,
        details=details,
        field_errors=field_errors,
        request_id=request_id,
    )
    return JSONResponse(status_code=status_code, content=envelope.model_dump())


def _request_id(request: Request) -> str | None:
    return request.headers.get("x-request-id") or request.headers.get("x-correlation-id")


def _from_http_detail(status_code: int, detail: Any) -> tuple[str, str, dict[str, Any]]:
    fallback_code = _status_code(status_code)
    fallback_message = _status_message(status_code)
    if status_code >= 500:
        return fallback_code, fallback_message, {}

    if isinstance(detail, dict):
        nested_error = detail.get("error")
        if isinstance(nested_error, dict):
            code = _string_or_default(nested_error.get("code"), fallback_code)
            message = _string_or_default(nested_error.get("message"), fallback_message)
            details = (
                nested_error.get("details") if isinstance(nested_error.get("details"), dict) else {}
            )
            return code, message, details

        code = _string_or_default(detail.get("code"), fallback_code)
        message = _string_or_default(
            detail.get("message") or detail.get("detail"),
            fallback_message,
        )
        details = detail.get("details") if isinstance(detail.get("details"), dict) else {}
        return code, message, details

    if isinstance(detail, str) and detail:
        return fallback_code, detail, {}

    return fallback_code, fallback_message, {}


def _validation_field_errors(exc: RequestValidationError) -> list[FieldError]:
    field_errors: list[FieldError] = []
    for error in exc.errors():
        loc = error.get("loc") or []
        field = ".".join(str(part) for part in loc)
        field_errors.append(
            FieldError(
                field=field,
                code=str(error.get("type") or "invalid"),
                message=str(error.get("msg") or "Invalid value."),
            )
        )
    return field_errors


def _status_code(status_code: int) -> str:
    return {
        400: "request.invalid",
        401: "auth.unauthorized",
        403: "auth.forbidden",
        404: "request.not_found",
        409: "request.conflict",
        422: "validation.failed",
        429: "rate_limit.exceeded",
        503: "dependency.unavailable",
    }.get(status_code, "internal.server_error" if status_code >= 500 else "request.invalid")


def _status_message(status_code: int) -> str:
    if status_code >= 500:
        return "An unexpected error occurred."
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Invalid request."


def _string_or_default(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value else default
