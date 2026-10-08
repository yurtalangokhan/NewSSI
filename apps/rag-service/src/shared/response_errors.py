# Copyright (c) 2026 Agentic AI Platform
"""Service-local transport adapters for the simple response model."""

import json
from typing import Any
from uuid import uuid4

from error_contract import (
    ApplicationError,
    InternalServerError,
    ValidationFailedError,
    render_error_message,
)
from fastapi import FastAPI, Request, Response, status as http_status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from localization import normalize_locale
from starlette.exceptions import HTTPException

from src.shared.api_versioning import API_PREFIX
from src.shared.observability import get_logger
from src.shared.response_models import ErrorModel, ResponseModel

logger = get_logger(__name__)
HTTP_ERROR_MINIMUM = http_status.HTTP_400_BAD_REQUEST


def request_locale(request: Request) -> str:
    """Resolve the requested language for public error messages."""
    return normalize_locale(
        request.query_params.get("lang")
        or request.query_params.get("locale")
        or request.headers.get("x-language")
        or request.headers.get("accept-language")
        or "en"
    )


def error_headers(error: ApplicationError, request: Request) -> dict[str, str]:
    """Preserve the existing language and correlation error headers."""
    headers = dict(error.headers)
    headers["Content-Language"] = request_locale(request)
    headers["X-Request-ID"] = (
        request.headers.get("x-request-id") or request.headers.get("x-correlation-id") or str(uuid4())
    )
    return headers


def set_error_response(response: Response, error: ApplicationError, request: Request) -> None:
    """Apply the failure status and existing transport headers to a route."""
    response.status_code = error.status_code
    response.headers.update(error_headers(error, request))


def error_response(error: ApplicationError, request: Request) -> JSONResponse:
    """Serialize an application failure with its HTTP status and headers."""
    normalize = getattr(error, "to_application_error", None)
    if callable(normalize):
        error = normalize()
    message = render_error_message(error, locale=request_locale(request))
    model = ResponseModel[None](
        statusCode=error.status_code,
        message=message,
        error=ErrorModel.from_error(error, message),
    )
    headers = error_headers(error, request)
    return JSONResponse(
        status_code=error.status_code,
        content=model.model_dump(mode="json"),
        headers=headers,
    )


def is_operational_path(path: str) -> bool:
    """Keep health, readiness and metrics outside application envelopes."""
    return path.rstrip("/") in {
        f"{API_PREFIX}/health",
        f"{API_PREFIX}/health/ready",
        f"{API_PREFIX}/graph/health",
        "/metrics",
    }


def register_response_errors(app: FastAPI) -> None:
    """Override only rag-service serialization; retain shared governance."""

    original_handlers = dict(app.exception_handlers)

    @app.exception_handler(ApplicationError)
    async def application_error(request: Request, error: ApplicationError) -> JSONResponse:
        """Render an application failure through the local response contract."""
        if is_operational_path(request.url.path):
            return await original_handlers[ApplicationError](request, error)
        return error_response(error, request)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _error: RequestValidationError) -> JSONResponse:
        """Render invalid request input through the local response contract."""
        if is_operational_path(request.url.path):
            return await original_handlers[RequestValidationError](request, _error)
        return error_response(ValidationFailedError(), request)

    original_http_handler = app.exception_handlers[HTTPException]

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        """Map framework HTTP failures to stable localized application messages."""
        # Keep the shared safe-detail mapping during the staged route migration.
        # It also preserves the existing HTTP error headers and 502 classification.
        if is_operational_path(request.url.path):
            return await original_handlers[HTTPException](request, error)
        original = await original_http_handler(request, error)
        public_error = json.loads(original.body)["error"]
        model = ResponseModel[None](
            statusCode=original.status_code,
            message=public_error["message"],
            error=ErrorModel(code=public_error["code"], message=public_error["message"]),
        )
        headers = dict(original.headers)
        headers.pop("content-length", None)
        return JSONResponse(
            status_code=original.status_code,
            content=model.model_dump(mode="json"),
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        """Log the original exception and return the public internal failure."""
        if is_operational_path(request.url.path):
            return await original_handlers[Exception](request, error)
        logger.error(
            "Unhandled rag-service request: %s %s",
            request.method,
            request.url.path,
            exc_info=(type(error), error, error.__traceback__),
        )
        return error_response(InternalServerError(), request)

    original_openapi = app.openapi

    def openapi() -> dict:
        """Publish the local error envelope while preserving endpoint DTO schemas."""
        schema = original_openapi()
        # Replace governance error schemas while preserving all endpoint DTOs.
        error_schema = ResponseModel[Any].model_json_schema()
        definitions = error_schema.pop("$defs", {})
        schema.setdefault("components", {}).setdefault("schemas", {}).update(definitions)

        error_schema = json.loads(json.dumps(error_schema).replace("#/$defs/", "#/components/schemas/"))
        schema["components"]["schemas"]["RagServiceErrorResponse"] = error_schema
        for path_name, path in schema.get("paths", {}).items():
            if is_operational_path(path_name):
                continue
            for operation in path.values():
                if not isinstance(operation, dict):
                    continue
                for status, response in operation.get("responses", {}).items():
                    if str(status).isdigit() and int(status) >= HTTP_ERROR_MINIMUM:
                        response["content"] = {
                            "application/json": {"schema": {"$ref": "#/components/schemas/RagServiceErrorResponse"}}
                        }
        return schema

    app.openapi = openapi
