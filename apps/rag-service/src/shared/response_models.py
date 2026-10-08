"""Simple JSON response model for HTTP routes."""

from typing import Any, Generic, TypeVar

from error_contract import ApplicationError
from pydantic import BaseModel

T = TypeVar("T")


class ErrorModel(BaseModel):
    """Stable public error code and request-localized message.

    ``details`` carries structured, client-actionable context (for example the
    per-node issues of a rejected flow). It is only ever populated for client
    errors: a server-side failure must not describe its internals to the caller.
    """

    code: str
    message: str
    details: dict[str, Any] | None = None

    @classmethod
    def from_error(cls, error: ApplicationError, message: str) -> "ErrorModel":
        public_details = dict(error.details) if error.status_code < 500 and error.details else None
        return cls(code=error.code, message=message, details=public_details)


class ResponseModel(BaseModel, Generic[T]):
    """Application JSON response; statusCode matches the HTTP status."""

    statusCode: int = 200  # noqa: N815 -- Public JSON contract uses statusCode.
    message: str | None = None
    data: T | None = None
    error: ErrorModel | None = None
