from dataclasses import dataclass, field
from typing import Any

from error_contract.composition import (
    CompositionError,
    ForbiddenTrustedFieldError,
    IncompatibleComponentError,
    MaxDepthError,
    MissingRequiredNestedError,
    MissingRequiredSettingError,
    NestedCycleError,
    SecretInConfigError,
    ToolInvocationError,
    ToolNotFoundError,
    UnavailableComponentError,
    UnknownComponentKeyError,
)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "CompositionError",
    "ForbiddenTrustedFieldError",
    "IncompatibleComponentError",
    "MaxDepthError",
    "MissingRequiredNestedError",
    "MissingRequiredSettingError",
    "NestedCycleError",
    "SecretInConfigError",
    "ToolInvocationError",
    "ToolNotFoundError",
    "UnavailableComponentError",
    "UnknownComponentKeyError",
    "ValidationIssue",
]
