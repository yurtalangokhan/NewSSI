from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


class CompositionError(Exception):
    """Base class for typed composition failures with a stable ``code``."""

    code: str = "composition_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}


class UnknownComponentKeyError(CompositionError):
    code = "unknown_component_key"


class UnavailableComponentError(CompositionError):
    code = "unavailable_component"


class MissingRequiredSettingError(CompositionError):
    code = "missing_required_setting"


class IncompatibleComponentError(CompositionError):
    code = "incompatible_component"


class NestedCycleError(CompositionError):
    code = "nested_cycle"


class MaxDepthError(CompositionError):
    code = "max_depth_exceeded"


class MissingRequiredNestedError(CompositionError):
    code = "missing_required_nested"


class SecretInConfigError(CompositionError):
    code = "secret_in_config"


class ForbiddenTrustedFieldError(CompositionError):
    code = "forbidden_trusted_field"


class ToolInvocationError(CompositionError):
    code = "tool_invocation_error"


class ToolNotFoundError(CompositionError):
    code = "tool_not_found"
