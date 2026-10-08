from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from typing import Any

from security import Redactor

from .errors import ForbiddenTrustedFieldError
from .ports import ToolInvocation, TrustedToolContext

# Transport header contract for the internal MCP/RAG path. The service token and
# any delegated credential travel only in these headers; they are never part of
# model-visible arguments or the tool result payload.
INTERNAL_AUTH_HEADER = "x-internal-token"
USER_ID_HEADER = "x-user-id"
TENANT_ID_HEADER = "x-tenant-id"
BINDING_REF_HEADER = "x-binding-ref"

# Keys that must never appear in model-visible tool arguments. Trusted values
# travel only inside the reserved internal envelope / transport headers.
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

# Field names that redaction must strip from logs, traces, checkpoints, errors,
# and tool results.
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


def build_trusted_context(
    *,
    user_id: str | None = None,
    tenant_id: str | None = None,
    binding_references: dict[str, str] | None = None,
    attachment_handles: tuple[str, ...] = (),
    project_id: str | None = None,
    request_id: str | None = None,
) -> TrustedToolContext:
    """The only sanctioned way to construct trusted context.

    Trusted context is built exclusively from authenticated request scope. It is
    never accepted from model output or user-provided runtime overrides.
    """
    return TrustedToolContext(
        user_id=user_id,
        tenant_id=tenant_id,
        binding_references=binding_references or {},
        attachment_handles=attachment_handles,
        project_id=project_id,
        request_id=request_id,
    )


def assert_model_arguments_trusted_free(model_arguments: dict[str, Any]) -> None:
    def _scan(value: Any) -> str | None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                if isinstance(key, str) and (
                    key.lower() in RESERVED_MODEL_ARGUMENT_KEYS or key.lower().startswith(f"{BINDING_REF_HEADER}-")
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

    for key in model_arguments:
        if isinstance(key, str) and key.lower() in RESERVED_MODEL_ARGUMENT_KEYS:
            raise ForbiddenTrustedFieldError(
                f"Model-visible argument '{key}' carries a trusted field.",
                details={"key": key},
            )


def binding_header_name(binding_key: str) -> str:
    """Transport header carrying a binding reference.

    Binding keys are dotted (``database_search.collection_ids``); on the wire the
    dot becomes ``__`` so proxies that reject dotted header names still forward it.
    """
    return f"{BINDING_REF_HEADER}-{binding_key.replace('.', '__')}"


def build_transport_headers(context: TrustedToolContext | None, internal_token: str) -> dict[str, str]:
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
        headers[binding_header_name(name)] = ref
    return headers


@dataclass(frozen=True)
class InternalToolEnvelope:
    """Reserved internal envelope for trusted tool calls on MCP/RAG transport.

    Model-visible arguments and trusted context are serialized together, but the
    trusted context is read only from transport headers by the receiving service
    and is never exposed to the model.
    """

    model_arguments: dict[str, Any] = field(default_factory=dict)
    trusted_context: TrustedToolContext | None = None
    transport_headers: dict[str, str] = field(default_factory=dict)

    def to_wire(self) -> str:
        assert_model_arguments_trusted_free(self.model_arguments)
        payload: dict[str, Any] = {
            "model_arguments": dict(self.model_arguments),
            "transport_headers": self.transport_headers,
        }
        return json.dumps(payload)

    @classmethod
    def from_wire(cls, wire: str) -> InternalToolEnvelope:
        data = json.loads(wire)
        if data.get("trusted_context") is not None:
            raise ForbiddenTrustedFieldError(
                "Trusted context must be supplied by transport headers.",
                details={"key": "trusted_context"},
            )
        model_arguments = data.get("model_arguments", {})
        assert_model_arguments_trusted_free(model_arguments)
        return cls(
            model_arguments=model_arguments,
            trusted_context=None,
            transport_headers=data.get("transport_headers", {}),
        )


# The field set and the placeholder stay here on purpose: tools-service and
# agent-service redact different names, and each has its own log convention.
# Only the traversal and masking are shared, so a fix to the traversal cannot
# be applied to one service and missed in the other.
_REDACTOR = Redactor(
    _REDACTED_FIELDS,
    prefixes=(f"{BINDING_REF_HEADER}-",),
    placeholder="***",
)


def redact_payload(value: Any) -> Any:
    """Return a copy with trusted/secret fields masked for logs and traces."""
    return _REDACTOR.payload(value)


def validate_invocation(invocation: ToolInvocation) -> None:
    """Reject invocations that smuggle trusted fields through model arguments."""
    assert_model_arguments_trusted_free(invocation.model_arguments)
