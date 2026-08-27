from __future__ import annotations

import json
from types import MappingProxyType

import pytest

from agent_composition import (
    BINDING_REF_HEADER,
    INTERNAL_AUTH_HEADER,
    TENANT_ID_HEADER,
    USER_ID_HEADER,
    ForbiddenTrustedFieldError,
    InMemoryToolBinding,
    InMemoryToolGateway,
    InternalToolEnvelope,
    ToolDescriptor,
    ToolInvocation,
    ToolResult,
    assert_model_arguments_trusted_free,
    build_transport_headers,
    build_trusted_context,
    redact_payload,
    validate_invocation,
)


def test_build_trusted_context_holds_only_opaque_refs() -> None:
    context = build_trusted_context(
        user_id="u1",
        tenant_id="t1",
        binding_references={"mail": "ref-abc"},
        attachment_handles=("att-1",),
        project_id="p1",
        request_id="r1",
    )
    assert context.user_id == "u1"
    assert context.binding_references == {"mail": "ref-abc"}
    assert context.attachment_handles == ("att-1",)
    # No secret bytes, tokens, or credentials are carried in the context.
    assert not hasattr(context, "token")
    assert not hasattr(context, "attachment_bytes")


def test_reserved_key_in_model_arguments_is_rejected() -> None:
    for key in (
        "trusted_context",
        "user_id",
        "tenant_id",
        "binding_references",
        "attachment_handles",
        "project_id",
        "request_id",
        INTERNAL_AUTH_HEADER,
        USER_ID_HEADER,
    ):
        with pytest.raises(ForbiddenTrustedFieldError):
            assert_model_arguments_trusted_free({key: "x"})


def test_nested_reserved_key_in_model_arguments_is_rejected() -> None:
    with pytest.raises(ForbiddenTrustedFieldError):
        assert_model_arguments_trusted_free({"filters": {"user_id": "u1"}})


def test_envelope_wire_payload_excludes_trusted_context_body() -> None:
    context = build_trusted_context(user_id="u1", tenant_id="t1", request_id="r1")
    envelope = InternalToolEnvelope(
        model_arguments={"query": "hi"},
        trusted_context=context,
        transport_headers={INTERNAL_AUTH_HEADER: "tok"},
    )
    wire = envelope.to_wire()
    payload = json.loads(wire)
    assert "trusted_context" not in payload
    assert payload["model_arguments"] == {"query": "hi"}
    restored = InternalToolEnvelope.from_wire(wire)
    assert restored.model_arguments == {"query": "hi"}
    assert restored.trusted_context is None


def test_envelope_from_wire_rejects_body_trusted_context() -> None:
    wire = json.dumps({"model_arguments": {"query": "hi"}, "trusted_context": {"user_id": "evil"}})
    with pytest.raises(ForbiddenTrustedFieldError):
        InternalToolEnvelope.from_wire(wire)


def test_invocation_and_trusted_context_copy_mapping_inputs() -> None:
    model_arguments = {"query": "hi"}
    binding_references = {"mail": "ref-1"}
    invocation = ToolInvocation(model_arguments=model_arguments)
    context = build_trusted_context(binding_references=binding_references)

    model_arguments["query"] = "changed"
    binding_references["mail"] = "changed"

    assert invocation.model_arguments == {"query": "hi"}
    assert isinstance(invocation.model_arguments, MappingProxyType)
    assert context.binding_references == {"mail": "ref-1"}
    assert isinstance(context.binding_references, MappingProxyType)


def test_validate_invocation_rejects_nested_reserved_key_after_dto_freeze() -> None:
    invocation = ToolInvocation(model_arguments={"filters": {"user_id": "u1"}})
    with pytest.raises(ForbiddenTrustedFieldError):
        validate_invocation(invocation)


def test_tool_result_metadata_is_deep_frozen() -> None:
    metadata = {"outer": {"token": "secret"}}
    output = {"nested": ["mutable"]}
    result = ToolResult(output=output, metadata=metadata)
    metadata["outer"]["token"] = "changed"
    output["nested"].append("changed")

    assert result.output["nested"] == ("mutable",)
    assert result.metadata["outer"]["token"] == "secret"
    assert isinstance(result.output, MappingProxyType)
    assert isinstance(result.metadata, MappingProxyType)
    assert isinstance(result.metadata["outer"], MappingProxyType)


def test_envelope_rejects_trusted_fields_in_model_arguments() -> None:
    envelope = InternalToolEnvelope(model_arguments={USER_ID_HEADER: "u1"})
    with pytest.raises(ForbiddenTrustedFieldError):
        envelope.to_wire()


def test_transport_headers_carry_token_and_identity_without_secrets() -> None:
    context = build_trusted_context(
        user_id="u1", tenant_id="t1", binding_references={"mail": "ref-1"}
    )
    headers = build_transport_headers(context, internal_token="internal-tok")
    assert headers[INTERNAL_AUTH_HEADER] == "internal-tok"
    assert headers[USER_ID_HEADER] == "u1"
    assert headers[TENANT_ID_HEADER] == "t1"
    assert headers[f"{BINDING_REF_HEADER}-mail"] == "ref-1"
    assert "token" not in headers or headers.get("token") is None


def test_redact_payload_masks_internal_token_and_bindings() -> None:
    payload = {
        INTERNAL_AUTH_HEADER: "super-secret",
        "binding_references": {"mail": "ref-1"},
        f"{BINDING_REF_HEADER}-mail": "ref-1",
        "result": "visible",
    }
    redacted = redact_payload(payload)
    assert redacted[INTERNAL_AUTH_HEADER] == "***"
    assert redacted["binding_references"] == "***"
    assert redacted[f"{BINDING_REF_HEADER}-mail"] == "***"
    assert redacted["result"] == "visible"


def test_validate_invocation_rejects_forged_trusted_field() -> None:
    invocation = ToolInvocation(model_arguments={INTERNAL_AUTH_HEADER: "x"})
    with pytest.raises(ForbiddenTrustedFieldError):
        validate_invocation(invocation)


@pytest.mark.asyncio
async def test_in_memory_gateway_resolves_selected_tools() -> None:
    async def _handler(invocation: ToolInvocation) -> ToolResult:
        return ToolResult(output=invocation.model_arguments)

    binding = InMemoryToolBinding(
        ToolDescriptor(key="search", description="search"),
        _handler,
    )
    gateway = InMemoryToolGateway([binding])
    await gateway.load()
    descriptors = await gateway.describe()
    assert [d.key for d in descriptors] == ["search"]
    resolved = await gateway.resolve(("search", "missing"))
    assert len(resolved) == 1
    assert resolved[0].descriptor.key == "search"
    result = await resolved[0].invoke(ToolInvocation(model_arguments={"q": 1}))
    assert result.output == {"q": 1}
    await gateway.close()
