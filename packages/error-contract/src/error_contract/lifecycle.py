"""Shared lifecycle failures used by service startup boundaries."""

from .exceptions import DependencyUnavailableError


class DependencyStartupError(DependencyUnavailableError, RuntimeError):
    """Safe startup error with dependency and remediation context."""

    code = "dependency.startup_failed"

    def __init__(self, *, dependency: str, operation_name: str, remediation: str) -> None:
        self.dependency = dependency
        self.operation_name = operation_name
        self.remediation = remediation
        super().__init__(
            message=(f"{dependency} is unavailable during startup {operation_name}. {remediation}"),
            message_key=self.message_key,
            details={
                "dependency": dependency,
                "operation": operation_name,
                "remediation": remediation,
            },
        )


__all__ = ["DependencyStartupError"]
