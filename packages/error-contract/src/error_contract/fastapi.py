import logging
import re
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from localization import normalize_locale
from starlette.exceptions import HTTPException as StarletteHTTPException

from ._request_id import resolve_request_id
from .exceptions import ApplicationError, InternalServerError, ValidationFailedError
from .localization import render_error_code_message, render_error_message
from .models import ErrorEnvelope, FieldError
from .openapi import ERROR_RESPONSES

logger = logging.getLogger(__name__)


def get_default_error_responses() -> dict[int | str, dict[str, Any]]:
    """Backwards-compatible alias for :data:`error_contract.ERROR_RESPONSES`."""
    return dict(ERROR_RESPONSES)


#: FastAPI's own defaults. Treated as "unset" so a service that never named its
#: API does not publish a spec titled "FastAPI" version "0.1.0".
_FASTAPI_DEFAULT_TITLE = "FastAPI"
_FASTAPI_DEFAULT_VERSION = "0.1.0"


def _resolve_identity(
    app: FastAPI,
    service_name: str,
    title: str | None,
    description: str | None,
    version: str | None,
) -> tuple[str, str, str]:
    app_title = None if app.title == _FASTAPI_DEFAULT_TITLE else app.title
    app_version = None if app.version == _FASTAPI_DEFAULT_VERSION else app.version
    readable = service_name.replace("-", " ").title()
    return (
        title or app_title or f"{readable} API",
        description or app.description or f"Enterprise HTTP API for {service_name}.",
        version or app_version or "1.0.0",
    )


def _apply_exception_handler(app: FastAPI) -> None:
    """Attach the error contract to every route, letting FastAPI resolve the model.

    Going through ``route.responses`` rather than editing the generated document
    means ``ErrorEnvelope`` lands in ``components/schemas`` with internally
    consistent references. Anything a route already declares wins, so a route
    that documents a richer 409 keeps it.
    """
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        merged: dict[int | str, dict[str, Any]] = dict(ERROR_RESPONSES)
        merged.update(route.responses or {})
        route.responses = merged


def _disambiguate_operation_ids(schema: dict[str, Any]) -> None:
    """Make every ``operationId`` unique, touching only the ones that collide.

    Services commonly derive the id from the handler's function name, which reads
    well but is not unique: a legacy and a canonical path for the same resource,
    or a DELETE and a POST spelling of one action, share a name. The spec
    requires uniqueness and generators key their method names on it, so a
    collision makes one of the endpoints uncallable from a generated client.

    Ids that were already unique are left exactly as they were — renaming them
    would churn every consumer for the sake of the few that were broken.
    """
    counts: dict[str, int] = {}
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict) and (oid := operation.get("operationId")):
                counts[oid] = counts.get(oid, 0) + 1

    colliding = {oid for oid, n in counts.items() if n > 1}
    if not colliding:
        return

    for path, path_item in schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if not isinstance(operation, dict):
                continue
            oid = operation.get("operationId")
            if oid not in colliding:
                continue
            slug = re.sub(r"\W+", "_", path).strip("_")
            operation["operationId"] = f"{oid}_{method.lower()}_{slug}"


def setup_governance_openapi(
    app: FastAPI,
    *,
    service_name: str,
    title: str | None = None,
    description: str | None = None,
    version: str | None = None,
    security_schemes: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Make the app's OpenAPI document satisfy the platform API standards.

    - API-001: ``info`` carries a real title, description and version
    - API-002: every operation has an ``operationId``
    - API-003/005: every operation documents its success response
    - API-004: every operation documents the error contract
    - API-006: ``components.securitySchemes`` describes how callers authenticate
    """
    svc_title, svc_description, svc_version = _resolve_identity(
        app, service_name, title, description, version
    )
    app.title, app.description, app.version = svc_title, svc_description, svc_version

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        _apply_exception_handler(app)
        schema = get_openapi(
            title=svc_title,
            version=svc_version,
            description=svc_description,
            routes=app.routes,
        )

        components = schema.setdefault("components", {})
        declared = components.setdefault("securitySchemes", {})
        if not declared:
            declared.update(security_schemes or _DEFAULT_SECURITY_SCHEMES)

        for path, path_item in schema.get("paths", {}).items():
            for method, operation in path_item.items():
                if not isinstance(operation, dict):
                    continue
                if not operation.get("operationId"):
                    slug = re.sub(r"[{}]", "", path).replace("/", "_").strip("_")
                    operation["operationId"] = f"{method.lower()}_{slug}"

        _disambiguate_operation_ids(schema)

        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi


#: Documents the JWT the API gateway validates. Services that enforce auth through
#: FastAPI dependencies publish their own schemes and this is not applied.
_DEFAULT_SECURITY_SCHEMES: dict[str, dict[str, Any]] = {
    "BearerAuth": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Keycloak-issued JWT access token, validated at the API gateway.",
    }
}


def register_error_handlers(
    app: FastAPI,
    *,
    service_name: str,
    title: str | None = None,
    description: str | None = None,
    version: str | None = None,
    security_schemes: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Register platform-standard error handlers and OpenAPI governance on a FastAPI app."""
    setup_governance_openapi(
        app,
        service_name=service_name,
        title=title,
        description=description,
        version=version,
        security_schemes=security_schemes,
    )

    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
        locale = _request_locale(request)
        to_application_error = getattr(exc, "to_application_error", None)
        if callable(to_application_error):
            exc = to_application_error()
        return _json_response(
            status_code=exc.status_code,
            code=exc.code,
            message=render_error_message(exc, locale=locale),
            details=exc.details,
            field_errors=exc.field_errors,
            request_id=_request_id(request),
            headers=exc.headers,
            locale=locale,
        )

    # Registered against Starlette's class, not FastAPI's. FastAPI's
    # ``HTTPException`` subclasses it, so this covers both — whereas registering
    # only the FastAPI class silently misses every error the router itself
    # raises (404 on an unknown path, 405 on a wrong method).
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        locale = _request_locale(request)
        code, message, details, is_literal = _from_http_detail(exc.status_code, exc.detail)
        if not is_literal:
            message = render_error_code_message(_status_code(exc.status_code), locale=locale)
        return _json_response(
            status_code=exc.status_code,
            code=code,
            message=message,
            details=details,
            request_id=_request_id(request),
            headers=_allowed_http_exception_headers(exc.headers),
            locale=locale,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        locale = _request_locale(request)
        error = ValidationFailedError()
        return _json_response(
            status_code=422,
            code=error.code,
            message=render_error_message(error, locale=locale),
            field_errors=_validation_field_errors(exc, locale=locale),
            request_id=_request_id(request),
            locale=locale,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        locale = _request_locale(request)
        # Resolved once and reused below: two separate calls could each mint
        # their own fallback uuid, leaving the log record's id unable to
        # correlate with what the client received.
        request_id = _request_id(request)
        logger.exception(
            "Unhandled %s request failed: %s %s -> internal.server_error",
            service_name,
            request.method,
            request.url.path,
            extra={
                "event": "http.request.unhandled_error",
                "service": service_name,
                "method": request.method,
                "path": request.url.path,
                "error_code": "internal.server_error",
                "safe_message": "An unexpected error occurred.",
                "request_id": request_id,
            },
        )
        return _json_response(
            status_code=500,
            code="internal.server_error",
            message=render_error_message(InternalServerError(), locale=locale),
            request_id=request_id,
            locale=locale,
        )


def _json_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    field_errors: list[FieldError] | None = None,
    request_id: str | None = None,
    headers: Mapping[str, str] | None = None,
    locale: str = "en",
) -> JSONResponse:
    envelope = ErrorEnvelope.from_error(
        code=code,
        message=message,
        details=details,
        field_errors=field_errors,
        request_id=request_id,
    )
    response_headers = dict(headers or {})
    response_headers["Content-Language"] = locale
    if request_id:
        response_headers["X-Request-ID"] = request_id
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(),
        headers=response_headers,
    )


def _request_id(request: Request) -> str:
    return resolve_request_id(request.headers)


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


def _allowed_http_exception_headers(headers: dict[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    allowed = {"retry-after", "www-authenticate"}
    return {name: value for name, value in headers.items() if name.lower() in allowed}


def _from_http_detail(status_code: int, detail: Any) -> tuple[str, str, dict[str, Any], bool]:
    fallback_code = _status_code(status_code)
    fallback_message = _status_message(status_code)
    if status_code >= 500:
        return fallback_code, fallback_message, {}, False

    if isinstance(detail, dict):
        nested_error = detail.get("error")
        if isinstance(nested_error, dict):
            code = _string_or_default(nested_error.get("code"), fallback_code)
            message = _string_or_default(nested_error.get("message"), fallback_message)
            details = (
                nested_error.get("details") if isinstance(nested_error.get("details"), dict) else {}
            )
            return code, message, details, bool(nested_error.get("message"))

        code = _string_or_default(detail.get("code"), fallback_code)
        message = _string_or_default(
            detail.get("message") or detail.get("detail"),
            fallback_message,
        )
        details = detail.get("details") if isinstance(detail.get("details"), dict) else {}
        return code, message, details, bool(detail.get("message") or detail.get("detail"))

    if isinstance(detail, str) and detail:
        standard = HTTPStatus._value2member_map_.get(status_code)
        if standard is not None and detail == standard.phrase:
            return fallback_code, fallback_message, {}, False
        return fallback_code, detail, {}, True

    return fallback_code, fallback_message, {}, False


def _validation_field_errors(
    exc: RequestValidationError,
    *,
    locale: str,
) -> list[FieldError]:
    field_errors: list[FieldError] = []
    for error in exc.errors():
        loc = error.get("loc") or []
        field = ".".join(str(part) for part in loc)
        error_type = str(error.get("type") or "invalid")
        message_key, fallback, params = _validation_message(error_type, error.get("ctx"))
        field_errors.append(
            FieldError(
                field=field,
                code=error_type,
                message=render_error_message(
                    ApplicationError(
                        message=fallback,
                        message_key=message_key,
                        message_params=params,
                    ),
                    locale=locale,
                ),
            )
        )
    return field_errors


def _validation_message(
    error_type: str,
    context: Any,
) -> tuple[str, str, dict[str, Any]]:
    simple_types = {
        "missing": ("errors.validation.field_required", "Field required"),
        "bool_parsing": ("errors.validation.invalid_boolean", "Must be a valid boolean."),
        "bool_type": ("errors.validation.invalid_boolean", "Must be a valid boolean."),
        "int_parsing": ("errors.validation.invalid_integer", "Must be a valid integer."),
        "int_type": ("errors.validation.invalid_integer", "Must be a valid integer."),
        "list_type": ("errors.validation.invalid_list", "Must be a valid list."),
        "dict_type": ("errors.validation.invalid_object", "Must be a valid object."),
        "string_type": ("errors.validation.invalid_string", "Must be a valid string."),
    }
    if error_type in simple_types:
        key, fallback = simple_types[error_type]
        return key, fallback, {}

    if error_type == "string_too_short":
        return (
            "errors.validation.string_too_short",
            "Invalid value.",
            _safe_context(context, "min_length"),
        )
    if error_type == "string_too_long":
        return (
            "errors.validation.string_too_long",
            "Invalid value.",
            _safe_context(context, "max_length"),
        )
    return "errors.validation.invalid_value", "Invalid value.", {}


def _safe_context(context: Any, name: str) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    value = context.get(name)
    if isinstance(value, int | float):
        return {name: value}
    return {}


def _status_code(status_code: int) -> str:
    return {
        400: "request.invalid",
        401: "auth.unauthorized",
        403: "auth.forbidden",
        404: "request.not_found",
        409: "request.conflict",
        413: "request.payload_too_large",
        415: "request.unsupported_media_type",
        422: "validation.failed",
        429: "rate_limit.exceeded",
        502: "dependency.invalid_response",
        503: "dependency.unavailable",
        504: "dependency.timeout",
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
