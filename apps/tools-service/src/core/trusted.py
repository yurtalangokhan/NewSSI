"""Trusted tool invocation contract for tools-service.

Defines the tools-service side of the agent composition trusted invocation
boundary. These types must stay in sync with the agent-service equivalents in
``agent_service.src.agent_composition.domain.ports`` and
``agent_service.src.agent_composition.domain.trusted_context`` — but tools-service
does not import those modules to keep the service boundary clean.

The contract enforces:
- Trusted context travels only in transport headers, never in model-visible args.
- Reserved keys in model arguments are rejected before any tool runs.
- Secrets are redacted from all observability surfaces.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

INTERNAL_AUTH_HEADER = "x-internal-token"
USER_ID_HEADER = "x-user-id"
TENANT_ID_HEADER = "x-tenant-id"
BINDING_REF_HEADER = "x-binding-ref"

RESERVED_MODEL_ARGUMENT_KEYS = frozenset(
    {
        "trusted_context",
        "trusted_context_ref",
        "user_id",
        "tenant_id",
        "binding_references",
        "attachment_handles",
        "project_id",
        "request_id",
        INTERNAL_AUTH_HEADER,
        USER_ID_HEADER,
        TENANT_ID_HEADER,
        BINDING_REF_HEADER,
    }
)

_REDACTED_FIELDS = frozenset(
    {
        INTERNAL_AUTH_HEADER,
        "token",
        "access_token",
        "secret",
        "password",
        "api_key",
        "binding_references",
        "trusted_context",
    }
)


class ForbiddenTrustedFieldError(Exception):
    code = "forbidden_trusted_field"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze_value(item) for item in value)
    return value


@dataclass(frozen=True)
class TrustedToolContext:
    """Request-scoped platform values never placed in model-visible arguments.

    Only opaque references and identity values are carried here. Never decrypted
    credentials, raw attachment bytes, access tokens, or the internal service token.
    """

    user_id: str | None = None
    tenant_id: str | None = None
    binding_references: Mapping[str, str] = field(default_factory=dict)
    attachment_handles: tuple[str, ...] = ()
    project_id: str | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "binding_references", _freeze_value(self.binding_references))


@dataclass(frozen=True)
class ToolDescriptor:
    key: str
    description: str
    required_trusted_bindings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolInvocation:
    model_arguments: Mapping[str, Any]
    trusted_context: TrustedToolContext | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_arguments", _freeze_value(self.model_arguments))


@dataclass(frozen=True)
class ToolResult:
    output: Any
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "output", _freeze_value(self.output))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))


def assert_model_arguments_trusted_free(model_arguments: Mapping[str, Any]) -> None:
    """Raise ForbiddenTrustedFieldError if model_arguments contains reserved keys."""

    def _scan(value: Any) -> str | None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                if isinstance(key, str) and (
                    key.lower() in RESERVED_MODEL_ARGUMENT_KEYS
                    or key.lower().startswith(f"{BINDING_REF_HEADER}-")
                ):
                    return key
                found = _scan(nested)
                if found is not None:
                    return found
        if isinstance(value, (list, tuple)):
            for item in value:
                found = _scan(item)
                if found is not None:
                    return found
        return None

    found_key = _scan(model_arguments)
    if found_key is not None:
        raise ForbiddenTrustedFieldError(
            f"Model-visible argument '{found_key}' carries a trusted field.",
            details={"key": found_key},
        )


def extract_trusted_context_from_headers(
    headers: dict[str, str],
) -> TrustedToolContext:
    """Extract TrustedToolContext from parsed HTTP headers.

    Values are read only from transport headers — never from query params,
    body fields, or model output.
    """
    binding_refs: dict[str, str] = {}
    attachment_handles: list[str] = []
    for name, value in headers.items():
        if isinstance(name, str) and name.lower().startswith(f"{BINDING_REF_HEADER}-"):
            binding_key = name[len(BINDING_REF_HEADER) + 1 :]
            binding_refs[binding_key] = value
        if isinstance(name, str) and name.lower().startswith("x-attachment-handle-"):
            attachment_handles.append(value)

    return TrustedToolContext(
        user_id=headers.get(USER_ID_HEADER),
        tenant_id=headers.get(TENANT_ID_HEADER),
        binding_references=binding_refs,
        attachment_handles=tuple(attachment_handles),
        project_id=headers.get("x-project-id"),
        request_id=headers.get("x-request-id"),
    )


def build_transport_headers(
    context: TrustedToolContext | None, internal_token: str
) -> dict[str, str]:
    """Build outgoing transport headers from a trusted context (for testing/tools)."""
    headers: dict[str, str] = {INTERNAL_AUTH_HEADER: internal_token}
    if context is None:
        return headers
    if context.user_id is not None:
        headers[USER_ID_HEADER] = context.user_id
    if context.tenant_id is not None:
        headers[TENANT_ID_HEADER] = context.tenant_id
    if context.project_id is not None:
        headers["x-project-id"] = context.project_id
    if context.request_id is not None:
        headers["x-request-id"] = context.request_id
    for index, handle in enumerate(context.attachment_handles):
        headers[f"x-attachment-handle-{index}"] = handle
    for name, ref in context.binding_references.items():
        headers[f"{BINDING_REF_HEADER}-{name}"] = ref
    return headers


def redact_payload(value: Any) -> Any:
    """Return a copy with trusted/secret fields masked for logs and traces."""
    if isinstance(value, dict):
        return {
            k: (
                "***REDACTED***"
                if isinstance(k, str)
                and (
                    k.lower() in _REDACTED_FIELDS
                    or k.lower().startswith(f"{BINDING_REF_HEADER}-")
                    or k.lower().startswith("x-attachment-handle-")
                )
                else redact_payload(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(redact_payload(v) for v in value)
    return value


def validate_invocation(invocation: ToolInvocation) -> None:
    """Reject invocations that smuggle trusted fields through model arguments."""
    assert_model_arguments_trusted_free(invocation.model_arguments)
