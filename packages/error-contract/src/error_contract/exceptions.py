from collections.abc import Mapping, Sequence
from typing import Any

from .models import FieldError

_MESSAGE_KEY_UNSET = object()


class ApplicationError(Exception):
    """Framework-neutral application error with a stable public contract."""

    status_code = 500
    code = "internal.server_error"
    message = "An unexpected error occurred."
    #: Response headers every instance of this error class carries by default
    #: (e.g. WWW-Authenticate on UnauthorizedError). Never mutated in place;
    #: __init__ only ever reads from it, so sharing the dict across instances
    #: is safe.
    headers: Mapping[str, str] = {}
    message_key: str | None = "errors.internal.server_error"

    def __init__(
        self,
        *,
        status_code: int | None = None,
        code: str | None = None,
        message: str | None = None,
        message_key: str | None | object = _MESSAGE_KEY_UNSET,
        message_params: Mapping[str, Any] | None = None,
        details: Mapping[str, Any] | None = None,
        field_errors: Sequence[FieldError] | None = None,
        headers: Mapping[str, str] | None = None,
        retry_after: int | float | None = None,
    ) -> None:
        self.status_code = status_code or self.status_code
        self.code = code or self.code
        self.message = message or self.message
        # The nearest declaration decides whether a message is literal or keyed.
        declaration = next(
            base
            for base in type(self).__mro__
            if "message" in base.__dict__ or "message_key" in base.__dict__
        )
        default_message_key = self.message_key if "message_key" in declaration.__dict__ else None
        self.message_key = (
            (None if message is not None else default_message_key)
            if message_key is _MESSAGE_KEY_UNSET
            else message_key
        )
        self.message_params = dict(message_params or {})
        self.details = dict(details or {})
        self.field_errors = list(field_errors or [])
        resolved_headers = dict(headers) if headers is not None else dict(self.__class__.headers)
        if retry_after is not None:
            # RFC 7231 SS7.1.3: tells the caller when a 429/503 is worth
            # retrying, instead of leaving them to guess a backoff.
            resolved_headers["Retry-After"] = str(int(retry_after))
        self.headers = resolved_headers
        super().__init__(self.message)


class BadRequestError(ApplicationError):
    status_code = 400
    code = "request.invalid"
    message = "Invalid request."
    message_key = "errors.request.invalid"


class MethodNotAllowedError(BadRequestError):
    status_code = 405
    code = "request.method_not_allowed"
    message_key = "errors.request.method_not_allowed"


class UnauthorizedError(ApplicationError):
    status_code = 401
    code = "auth.unauthorized"
    message = "Authentication is required."
    #: RFC 7235 SS4.1: a 401 MUST advertise how to authenticate. The platform's
    #: own OpenAPI security scheme (see fastapi.py's _DEFAULT_SECURITY_SCHEMES)
    #: is Bearer, so that is the default here too.
    headers = {"WWW-Authenticate": "Bearer"}
    message_key = "errors.auth.unauthorized"


class ForbiddenError(ApplicationError):
    status_code = 403
    code = "auth.forbidden"
    message = "You do not have permission to perform this action."
    message_key = "errors.auth.forbidden"


class NotFoundError(ApplicationError):
    status_code = 404
    code = "request.not_found"
    message = "Resource not found."
    message_key = "errors.request.not_found"


class ConflictError(ApplicationError):
    status_code = 409
    code = "request.conflict"
    message = "The request conflicts with the current state."
    message_key = "errors.request.conflict"


class ValidationFailedError(ApplicationError):
    status_code = 422
    code = "validation.failed"
    message = "Request validation failed."
    message_key = "errors.validation.failed"


class RateLimitedError(ApplicationError):
    status_code = 429
    code = "rate_limit.exceeded"
    message = "Too many requests. Try again later."
    message_key = "errors.rate_limit.exceeded"


class DependencyUnavailableError(ApplicationError):
    status_code = 503
    code = "dependency.unavailable"
    message = "A required dependency is unavailable."
    message_key = "errors.dependency.unavailable"


class DependencyConnectionError(DependencyUnavailableError):
    status_code = 503
    code = "dependency.connection_failed"
    message = "A required dependency could not be reached."
    message_key = "errors.dependency.connection_failed"


class DatabaseConnectionError(DependencyUnavailableError):
    status_code = 503
    code = "database.connection_failed"
    message = "Database connection failed."
    message_key = "errors.database.connection_failed"


class DatabaseTimeoutError(DependencyUnavailableError):
    status_code = 503
    code = "database.timeout"
    message = "Database operation timed out."
    message_key = "errors.database.timeout"


class DatabaseOperationError(ApplicationError):
    status_code = 500
    code = "database.operation_failed"
    message = "Database operation failed."
    message_key = "errors.database.operation_failed"


class DependencyTimeoutError(DependencyUnavailableError):
    status_code = 504
    code = "dependency.timeout"
    message = "A required dependency timed out."
    message_key = "errors.dependency.timeout"


class DependencyResponseError(DependencyUnavailableError):
    status_code = 502
    code = "dependency.invalid_response"
    message = "A required dependency returned an invalid response."
    message_key = "errors.dependency.invalid_response"


class DependencyAuthenticationError(DependencyUnavailableError):
    status_code = 502
    code = "dependency.authentication_failed"
    message = "Authentication with a required dependency failed."
    message_key = "errors.dependency.authentication_failed"


class DependencyRateLimitedError(DependencyUnavailableError):
    status_code = 503
    code = "dependency.rate_limited"
    message = "A required dependency rate limited the request."
    message_key = "errors.dependency.rate_limited"


class ConfigurationError(ApplicationError):
    status_code = 500
    code = "configuration.invalid"
    message = "Server configuration is invalid."
    message_key = "errors.configuration.invalid"


class PayloadTooLargeError(ApplicationError):
    status_code = 413
    code = "request.payload_too_large"
    message = "The request payload is too large."
    message_key = "errors.request.payload_too_large"


class UnsupportedMediaTypeError(ApplicationError):
    status_code = 415
    code = "request.unsupported_media_type"
    message = "The request media type is not supported."
    message_key = "errors.request.unsupported_media_type"


class OperationTimeoutError(ApplicationError):
    status_code = 504
    code = "operation.timeout"
    message = "The operation timed out."
    message_key = "errors.operation.timeout"


class OperationExecutionError(ApplicationError):
    status_code = 500
    code = "operation.failed"
    message = "The operation failed."
    message_key = "errors.operation.failed"


class InternalServerError(ApplicationError):
    status_code = 500
    code = "internal.server_error"
    message = "An unexpected error occurred."
    message_key = "errors.internal.server_error"
