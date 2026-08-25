from typing import Any

from pydantic import BaseModel, Field


class FieldError(BaseModel):
    field: str
    code: str
    message: str


class ApiError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    field_errors: list[FieldError] = Field(default_factory=list)
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    error: ApiError

    @classmethod
    def from_error(
        cls,
        *,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        field_errors: list[FieldError] | None = None,
        request_id: str | None = None,
    ) -> "ErrorEnvelope":
        return cls(
            error=ApiError(
                code=code,
                message=message,
                details=details or {},
                field_errors=field_errors or [],
                request_id=request_id,
            )
        )
