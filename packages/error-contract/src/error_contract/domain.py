from collections.abc import Sequence
from typing import Any

from .exceptions import (
    ApplicationError,
    BadRequestError,
    ConfigurationError,
    DependencyUnavailableError,
    ForbiddenError,
    NotFoundError,
    PayloadTooLargeError,
    ValidationFailedError,
)


class DelegatedIdentityRequiredError(ForbiddenError):
    code = "auth.delegation_required"
    message_key = "errors.auth.delegation_required"


class TrustedIdentityRequiredError(ForbiddenError):
    code = "auth.trusted_identity_required"
    message_key = "errors.auth.trusted_identity_required"


class GraphSearchPermissionError(ForbiddenError):
    code = "retrieval.graph_permission_required"
    message_key = "errors.retrieval.graph_permission_required"


class CollectionAccessDeniedError(ForbiddenError):
    code = "collection.access_denied"
    message_key = "errors.collection.access_denied"


class MemoryUpsertError(DependencyUnavailableError):
    code = "memory.upsert_failed"
    message_key = "errors.memory.upsert_failed"


class MemoryDeleteError(DependencyUnavailableError):
    code = "memory.delete_failed"
    message_key = "errors.memory.delete_failed"


class RequiredFieldError(ValidationFailedError):
    """A required domain value is empty, with a localizable field name."""

    code = "validation.field_required"
    message_key = "errors.validation.field_required_named"
    default_message_params = {"field": "value"}

    def __init__(self, field: str = "value", **kwargs: Any) -> None:
        kwargs.setdefault("message_params", {"field": field})
        kwargs.setdefault("details", {"field": field})
        super().__init__(**kwargs)


class ApiKeyNotFoundError(NotFoundError):
    code = "api_key.not_found"
    message_key = "errors.user_service.api_key.not_found"


class MemoryNotFoundError(NotFoundError):
    code = "memory.not_found"
    message_key = "errors.user_service.memory.not_found"


class PromptShortcutNotFoundError(NotFoundError):
    code = "settings.shortcut_not_found"
    message_key = "errors.settings.shortcut_not_found"


class UserNotFoundError(NotFoundError):
    code = "user.not_found"
    message_key = "errors.user.not_found"


class CollectionNotFoundError(NotFoundError):
    """A collection is missing or inaccessible to the caller."""

    code = "collection.not_found"
    message_key = "errors.collection.not_found"


class GatewayRoutingError(ConfigurationError):
    """A configured service URL bypasses the API gateway."""


class WorkspaceEscapeError(ForbiddenError):
    """A requested workspace path resolves outside the caller's workspace."""

    def __init__(self, message: str = "Path escapes the workspace.") -> None:
        super().__init__(message=message, message_key="errors.auth.forbidden")


class UnknownCommandError(ValidationFailedError, ValueError):
    """A requested command is not in the server-owned command registry."""

    def __init__(self, message: str = "Unknown command.") -> None:
        super().__init__(message=message, message_key="errors.validation.failed")


class GitArgumentError(BadRequestError, ValueError):
    """A caller supplied an invalid or unsafe Git argument."""

    def __init__(self, message: str = "Invalid Git argument.") -> None:
        super().__init__(message=message, message_key="errors.request.invalid")


class UnsafeExpressionError(ValidationFailedError, ValueError):
    """An arithmetic expression contains an unsupported operation."""

    def __init__(self, message: str = "Invalid arithmetic expression.") -> None:
        super().__init__(message=message, message_key="errors.validation.failed")


class UnsafeTemplateError(ValidationFailedError, ValueError):
    """A template contains unsupported field access or formatting."""

    def __init__(self, message: str = "Invalid template.") -> None:
        super().__init__(message=message, message_key="errors.validation.failed")


class RejectedUploadError(ValidationFailedError, ValueError):
    """An uploaded file is invalid or its declared type does not match."""

    def __init__(
        self,
        message: str = "Uploaded file is invalid.",
        *,
        message_key: str = "errors.validation.failed",
    ) -> None:
        super().__init__(message=message, message_key=message_key)


class UploadTooLargeError(PayloadTooLargeError, ValueError):
    """An upload exceeded a configured size or count limit."""

    def __init__(self, message: str = "The upload exceeds the configured limit.") -> None:
        super().__init__(message=message, message_key="errors.request.payload_too_large")


class FlowError(ApplicationError):
    """Base class for agent flow canvas errors."""

    code = "agent.flow_error"
    message_key = "errors.flow.failed"

    def __init__(self, message: str = "Flow operation failed.") -> None:
        super().__init__(message=message, code=self.code, message_key=self.message_key)


class DuplicateComponentError(FlowError):
    code = "agent.component_duplicate"
    message_key = "errors.flow.component_duplicate"
    status_code = 409

    def __init__(self, component_type: str) -> None:
        self.component_type = component_type
        super().__init__(f"Component type {component_type!r} is already registered")


class UnknownComponentError(FlowError):
    code = "agent.component_unknown"
    message_key = "errors.flow.component_unknown"
    status_code = 422

    def __init__(self, component_type: str) -> None:
        self.component_type = component_type
        super().__init__(f"Unknown component type: {component_type!r}")


class UnknownOptionsSourceError(FlowError):
    code = "agent.options_source_unknown"
    message_key = "errors.flow.options_source_unknown"
    status_code = 422

    def __init__(self, source: str) -> None:
        self.source = source
        super().__init__(f"Unknown options source: {source!r}")


class NotAResourceNodeError(FlowError):
    code = "agent.node_not_resource"
    message_key = "errors.flow.node_not_resource"
    status_code = 422

    def __init__(self, node_id: str, component_type: str) -> None:
        self.node_id = node_id
        self.component_type = component_type
        super().__init__(f"Node {node_id!r} (type {component_type!r}) is not a resource node")


class FlowBuildError(FlowError):
    code = "agent.flow_build_failed"
    message_key = "errors.flow.build_failed"


class FlowVersionConflictError(FlowError):
    code = "agent.flow_version_conflict"
    message_key = "errors.flow.version_conflict"
    status_code = 409


class FlowValidationError(FlowError):
    code = "agent.flow_validation_failed"
    message_key = "errors.flow.validation_failed"
    status_code = 422

    def __init__(self, issues: Sequence[Any]) -> None:
        self.issues = issues
        super().__init__(f"Flow failed validation with {len(issues)} error(s)")


class FlowNotPublishedError(FlowError):
    code = "agent.flow_not_published"
    message_key = "errors.flow.not_published"
    status_code = 404

    def __init__(self, persona_id: int) -> None:
        self.persona_id = persona_id
        super().__init__(f"Flow for persona '{persona_id}' has no published version yet")


class MissingMigrationError(FlowError):
    code = "agent.flow_migration_missing"
    message_key = "errors.flow.migration_missing"
    status_code = 422

    def __init__(self, component_type: str, from_version: int) -> None:
        self.component_type = component_type
        self.from_version = from_version
        super().__init__(
            f"No migration registered for {component_type!r} from version "
            f"{from_version}. Register one with "
            f"register_migration({component_type!r}, {from_version}, ...)."
        )


class CompositionValidationError(ValidationFailedError, ValueError):
    """Base error for composition validation failures."""

    code = "composition.validation_failed"

    def __init__(self, message: str = "Agent composition is invalid.") -> None:
        super().__init__(message=message, code=self.code, message_key=self.message_key)


class CircularDependencyError(CompositionValidationError):
    pass


class SchemaMismatchError(CompositionValidationError):
    pass


class MaxDepthExceededError(CompositionValidationError):
    pass


class MissingAgentError(CompositionValidationError):
    pass


class SSRFError(ApplicationError):
    """Base error for rejected or unresolved outbound URLs."""

    code = "security.url_rejected"
    message_key = "errors.security.url_rejected"
    status_code = 400

    def __init__(self, message: str = "The requested URL is not allowed.") -> None:
        super().__init__(message=message, code=self.code, message_key=self.message_key)


class SSRFBlockedError(SSRFError):
    code = "security.url_blocked"
    message_key = "errors.security.url_blocked"
    status_code = 403


class DNSResolutionError(SSRFError):
    code = "security.dns_resolution_failed"
    message_key = "errors.security.dns_resolution_failed"


SSRFException = SSRFError
SSRFBlockedException = SSRFBlockedError


__all__ = [
    "ApiKeyNotFoundError",
    "MemoryNotFoundError",
    "PromptShortcutNotFoundError",
    "UserNotFoundError",
    "DelegatedIdentityRequiredError",
    "TrustedIdentityRequiredError",
    "GraphSearchPermissionError",
    "CollectionAccessDeniedError",
    "MemoryUpsertError",
    "MemoryDeleteError",
    "RequiredFieldError",
    "CollectionNotFoundError",
    "GatewayRoutingError",
    "GitArgumentError",
    "RejectedUploadError",
    "UploadTooLargeError",
    "UnsafeExpressionError",
    "UnsafeTemplateError",
    "UnknownCommandError",
    "WorkspaceEscapeError",
    "SSRFError",
    "SSRFBlockedError",
    "CircularDependencyError",
    "CompositionValidationError",
    "DNSResolutionError",
    "DuplicateComponentError",
    "FlowBuildError",
    "FlowError",
    "FlowNotPublishedError",
    "FlowValidationError",
    "FlowVersionConflictError",
    "MaxDepthExceededError",
    "MissingAgentError",
    "MissingMigrationError",
    "NotAResourceNodeError",
    "SSRFBlockedException",
    "SSRFException",
    "SchemaMismatchError",
    "UnknownComponentError",
    "UnknownOptionsSourceError",
]


class GraphExecutionLimitError(ValidationFailedError):
    """The graph exhausted the execution budget for one turn."""

    code = "agent.execution_limit_exceeded"
    message_key = "errors.agent.execution_limit_exceeded"
