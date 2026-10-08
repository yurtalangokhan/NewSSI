from pathlib import Path
from string import Formatter
from typing import Any

from localization import init_localization, normalize_locale, t

from .agent import (
    AgentClientError,
    AgentError,
    AgentExpansionError,
    AgentNotFoundError,
    AgentPermissionError,
    GraphBuilderError,
    InvalidQuestionsError,
    MCPAuthError,
)
from .composition import (
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
from .connectors import (
    ConnectorAccessError,
    ConnectorKafkaConfigurationError,
    ConnectorKafkaError,
    ConnectorKafkaValidationError,
    ConnectorSqlConfigurationError,
    ConnectorSqlError,
    ConnectorSqlValidationError,
    MicrosoftAuthenticationError,
    MicrosoftConfigurationError,
    MicrosoftConnectorError,
    MicrosoftValidationError,
)
from .domain import (
    ApiKeyNotFoundError,
    CircularDependencyError,
    CollectionAccessDeniedError,
    CollectionNotFoundError,
    CompositionValidationError,
    DelegatedIdentityRequiredError,
    DNSResolutionError,
    DuplicateComponentError,
    FlowBuildError,
    FlowError,
    FlowNotPublishedError,
    FlowValidationError,
    FlowVersionConflictError,
    GatewayRoutingError,
    GitArgumentError,
    GraphExecutionLimitError,
    GraphSearchPermissionError,
    MaxDepthExceededError,
    MemoryDeleteError,
    MemoryNotFoundError,
    MemoryUpsertError,
    MissingAgentError,
    MissingMigrationError,
    NotAResourceNodeError,
    PromptShortcutNotFoundError,
    RejectedUploadError,
    RequiredFieldError,
    SchemaMismatchError,
    SSRFBlockedError,
    SSRFError,
    TrustedIdentityRequiredError,
    UnknownCommandError,
    UnknownComponentError,
    UnknownOptionsSourceError,
    UnsafeExpressionError,
    UnsafeTemplateError,
    UploadTooLargeError,
    UserNotFoundError,
    WorkspaceEscapeError,
)
from .exceptions import (
    ApplicationError,
    BadRequestError,
    ConfigurationError,
    ConflictError,
    DatabaseConnectionError,
    DatabaseOperationError,
    DatabaseTimeoutError,
    DependencyAuthenticationError,
    DependencyConnectionError,
    DependencyRateLimitedError,
    DependencyResponseError,
    DependencyTimeoutError,
    DependencyUnavailableError,
    ForbiddenError,
    InternalServerError,
    MethodNotAllowedError,
    NotFoundError,
    OperationExecutionError,
    OperationTimeoutError,
    PayloadTooLargeError,
    RateLimitedError,
    UnauthorizedError,
    UnsupportedMediaTypeError,
    ValidationFailedError,
)
from .idempotency import (
    IdempotencyInProgressError,
    IdempotencyKeyInvalidError,
    IdempotencyKeyRequiredError,
    IdempotencyKeyReusedError,
    IdempotencyStoreUnavailableError,
)
from .lifecycle import DependencyStartupError

init_localization(Path(__file__).with_name("locales"))

_ERROR_TYPES = (
    ApiKeyNotFoundError,
    MemoryNotFoundError,
    PromptShortcutNotFoundError,
    UserNotFoundError,
    DelegatedIdentityRequiredError,
    TrustedIdentityRequiredError,
    GraphExecutionLimitError,
    GraphSearchPermissionError,
    CollectionAccessDeniedError,
    MemoryUpsertError,
    MemoryDeleteError,
    RequiredFieldError,
    CollectionNotFoundError,
    BadRequestError,
    MethodNotAllowedError,
    UnauthorizedError,
    ForbiddenError,
    NotFoundError,
    ConflictError,
    ValidationFailedError,
    RateLimitedError,
    DependencyUnavailableError,
    DependencyConnectionError,
    AgentError,
    InvalidQuestionsError,
    GraphBuilderError,
    AgentClientError,
    AgentPermissionError,
    AgentNotFoundError,
    AgentExpansionError,
    MCPAuthError,
    DuplicateComponentError,
    UnknownComponentError,
    UnknownOptionsSourceError,
    NotAResourceNodeError,
    FlowError,
    FlowBuildError,
    FlowVersionConflictError,
    FlowValidationError,
    FlowNotPublishedError,
    MissingMigrationError,
    CompositionValidationError,
    CircularDependencyError,
    SchemaMismatchError,
    MaxDepthExceededError,
    MissingAgentError,
    SSRFError,
    SSRFBlockedError,
    DNSResolutionError,
    CompositionError,
    UnknownComponentKeyError,
    UnavailableComponentError,
    MissingRequiredSettingError,
    IncompatibleComponentError,
    NestedCycleError,
    MaxDepthError,
    MissingRequiredNestedError,
    SecretInConfigError,
    ForbiddenTrustedFieldError,
    ToolInvocationError,
    ToolNotFoundError,
    ConnectorAccessError,
    ConnectorKafkaError,
    ConnectorSqlError,
    MicrosoftConnectorError,
    ConnectorKafkaConfigurationError,
    ConnectorKafkaValidationError,
    ConnectorSqlConfigurationError,
    ConnectorSqlValidationError,
    MicrosoftAuthenticationError,
    MicrosoftConfigurationError,
    MicrosoftValidationError,
    IdempotencyKeyRequiredError,
    IdempotencyKeyInvalidError,
    IdempotencyKeyReusedError,
    IdempotencyInProgressError,
    IdempotencyStoreUnavailableError,
    GatewayRoutingError,
    GitArgumentError,
    RejectedUploadError,
    UploadTooLargeError,
    UnsafeExpressionError,
    UnsafeTemplateError,
    UnknownCommandError,
    WorkspaceEscapeError,
    DatabaseConnectionError,
    DatabaseTimeoutError,
    DatabaseOperationError,
    DependencyTimeoutError,
    DependencyResponseError,
    DependencyAuthenticationError,
    DependencyRateLimitedError,
    ConfigurationError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
    OperationTimeoutError,
    OperationExecutionError,
    InternalServerError,
    DependencyStartupError,
)
# Only declarations own a code; subclasses sharing it retain its canonical metadata.
_ERROR_BY_CODE: dict[str, type[ApplicationError]] = {}
for _error_type in _ERROR_TYPES:
    if "code" in _error_type.__dict__:
        _ERROR_BY_CODE.setdefault(_error_type.code, _error_type)

_CONNECTOR_DEFAULTS = {
    "authorization": "You do not have permission to access this connector.",
    "configuration": "Connector configuration is invalid.",
    "validation": "Connector input is invalid.",
    "connection": "The connector could not be reached.",
    "timeout": "The connector operation timed out.",
    "authentication": "Connector authentication failed.",
    "unsupported": "The connector operation is not supported.",
    "response": "The connector returned an invalid response.",
}


def render_error_message(error: ApplicationError, locale: str | None = None) -> str:
    """Render public error metadata without mutating the exception."""
    if not error.message_key:
        return error.message

    rendered = t(
        error.message_key,
        locale=normalize_locale(locale) if locale else None,
        **error.message_params,
    )
    if _is_safe_render(rendered, error.message_key):
        return rendered
    if _is_safe_render(error.message, error.message_key):
        return error.message
    return _render_internal_fallback(locale)


def render_error_code_message(
    code: str,
    locale: str | None = None,
    *,
    message_params: dict[str, Any] | None = None,
) -> str:
    """Render a known stable error code for non-HTTP adapters such as SSE and MCP."""
    params = dict(message_params or {})
    if code.startswith("connector.") and code.removeprefix("connector.") in _CONNECTOR_DEFAULTS:
        category = code.removeprefix("connector.")
        fallback = _CONNECTOR_DEFAULTS[category]
        key = f"errors.connector.{category}"
        params.setdefault("message", fallback)
    else:
        error_type = _ERROR_BY_CODE.get(code, InternalServerError)
        fallback = error_type.message
        key = error_type.message_key
        params = {**getattr(error_type, "default_message_params", {}), **params}
    # Specialized domain constructors may require diagnostic arguments. Rendering
    # a code uses only its public metadata and never executes those constructors.
    error = ApplicationError(message=fallback, message_key=key, message_params=params)
    return render_error_message(error, locale=locale)


def _render_internal_fallback(locale: str | None) -> str:
    key = InternalServerError.message_key
    rendered = t(key, locale=normalize_locale(locale) if locale else None)
    if _is_safe_render(rendered, key):
        return rendered
    return InternalServerError.message


def _is_safe_render(message: str, key: str | None) -> bool:
    if not message or message == key:
        return False
    try:
        return not any(field_name for _, field_name, _, _ in Formatter().parse(message))
    except ValueError:
        return False


__all__ = ["render_error_code_message", "render_error_message"]
