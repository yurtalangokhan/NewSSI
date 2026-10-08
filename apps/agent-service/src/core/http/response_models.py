"""Simple JSON response model for agent-service routes."""

import json
from typing import Any, Generic, TypeVar

from error_contract import ApplicationError
from pydantic import BaseModel, Field

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


class StreamEventModel(BaseModel, Generic[T]):
    """Typed event boundary for SSE; HTTP status belongs to the open response.

    The serializer writes event as the SSE event name and data as the existing
    event payload. Optional error metadata describes a localized stream failure.
    """

    event: str = Field(min_length=1, pattern=r"^[^\r\n]+$")
    data: T | None = None
    error: ErrorModel | None = None

    def to_sse(self, *, named: bool = False) -> str:
        """Serialize an SSE frame while retaining existing payload fields.

        Named events opt in to an event line. Existing data-only producers keep
        their browser message events and payload discriminators unchanged.
        """
        payload = self.data
        if self.error is not None:
            payload = {
                **(payload if isinstance(payload, dict) else {"data": payload}),
                "error": self.error.model_dump(mode="json"),
            }
        prefix = f"event: {self.event}\n" if named else ""
        return f"{prefix}data: {json.dumps(payload)}\n\n"
