from collections.abc import Mapping
from typing import Any

from .exceptions import ApplicationError


class CompositionError(ApplicationError):
    """Base class for typed composition failures with a stable code."""

    code = "composition_error"
    message_key = "errors.internal.server_error"

    def __init__(
        self,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, message_key=self.message_key, details=details)


class UnknownComponentKeyError(CompositionError):
    code = "unknown_component_key"
    status_code = 422
    message_key = "errors.validation.failed"


class UnavailableComponentError(CompositionError):
    code = "unavailable_component"
    status_code = 503
    message_key = "errors.dependency.unavailable"


class MissingRequiredSettingError(CompositionError):
    code = "missing_required_setting"
    status_code = 422
    message_key = "errors.validation.failed"


class IncompatibleComponentError(CompositionError):
    code = "incompatible_component"
    status_code = 422
    message_key = "errors.validation.failed"


class NestedCycleError(CompositionError):
    code = "nested_cycle"
    status_code = 422
    message_key = "errors.validation.failed"


class MaxDepthError(CompositionError):
    code = "max_depth_exceeded"
    status_code = 422
    message_key = "errors.validation.failed"


class MissingRequiredNestedError(CompositionError):
    code = "missing_required_nested"
    status_code = 422
    message_key = "errors.validation.failed"


class SecretInConfigError(CompositionError):
    code = "secret_in_config"
    status_code = 400
    message_key = "errors.request.invalid"


class ForbiddenTrustedFieldError(CompositionError):
    code = "forbidden_trusted_field"
    status_code = 400
    message_key = "errors.security.trusted_field_forbidden"

    def __init__(
        self,
        message: str = "Trusted identity fields are not accepted here.",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)


class ToolInvocationError(CompositionError):
    code = "tool_invocation_error"
    status_code = 503
    message_key = "errors.dependency.unavailable"


class ToolNotFoundError(CompositionError):
    code = "tool_not_found"
    status_code = 404
    message_key = "errors.request.not_found"
