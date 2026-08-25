from collections.abc import Mapping, Sequence
from typing import Any

from .models import FieldError


class ApplicationError(Exception):
    """Framework-neutral application error with a stable public contract."""

    status_code = 500
    code = "internal.server_error"
    message = "An unexpected error occurred."

    def __init__(
        self,
        *,
        status_code: int | None = None,
        code: str | None = None,
        message: str | None = None,
        details: Mapping[str, Any] | None = None,
        field_errors: Sequence[FieldError] | None = None,
    ) -> None:
        self.status_code = status_code or self.status_code
        self.code = code or self.code
        self.message = message or self.message
        self.details = dict(details or {})
        self.field_errors = list(field_errors or [])
        super().__init__(self.message)


class BadRequestError(ApplicationError):
    status_code = 400
    code = "request.invalid"
    message = "Invalid request."


class UnauthorizedError(ApplicationError):
    status_code = 401
    code = "auth.unauthorized"
    message = "Authentication is required."


class ForbiddenError(ApplicationError):
    status_code = 403
    code = "auth.forbidden"
    message = "You do not have permission to perform this action."


class NotFoundError(ApplicationError):
    status_code = 404
    code = "request.not_found"
    message = "Resource not found."


class ConflictError(ApplicationError):
    status_code = 409
    code = "request.conflict"
    message = "The request conflicts with the current state."


class ValidationFailedError(ApplicationError):
    status_code = 422
    code = "validation.failed"
    message = "Request validation failed."


class RateLimitedError(ApplicationError):
    status_code = 429
    code = "rate_limit.exceeded"
    message = "Too many requests. Try again later."


class DependencyUnavailableError(ApplicationError):
    status_code = 503
    code = "dependency.unavailable"
    message = "A required dependency is unavailable."
