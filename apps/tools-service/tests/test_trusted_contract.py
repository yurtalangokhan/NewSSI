"""Tests for the ASC-2A trusted tool invocation contract in tools-service."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from src.core.trusted import (
    BINDING_REF_HEADER,
    INTERNAL_AUTH_HEADER,
    TENANT_ID_HEADER,
    USER_ID_HEADER,
    ForbiddenTrustedFieldError,
    ToolDescriptor,
    ToolInvocation,
    ToolResult,
    TrustedToolContext,
    assert_model_arguments_trusted_free,
    build_transport_headers,
    extract_trusted_context_from_headers,
    redact_payload,
    validate_invocation,
)
from src.core.trusted_context import (
    get_current_trusted_context,
    set_current_trusted_context,
)
from src.core.trusted_middleware import TrustedContextMiddleware


class TestTrustedContextTypes:
    def test_trusted_tool_context_frozen(self) -> None:
        ctx = TrustedToolContext(
            user_id="u123",
            tenant_id="t456",
            binding_references={"mail": "mbind_abc"},
            attachment_handles=("att-1",),
            project_id="p789",
            request_id="r001",
        )
        assert ctx.user_id == "u123"
        assert ctx.tenant_id == "t456"
        assert ctx.binding_references == {"mail": "mbind_abc"}
        assert ctx.attachment_handles == ("att-1",)
        assert ctx.project_id == "p789"
        assert ctx.request_id == "r001"

    def test_tool_invocation_frozen(self) -> None:
        ctx = TrustedToolContext(user_id="u123")
        inv = ToolInvocation(model_arguments={"query": "hello"}, trusted_context=ctx)
        assert inv.model_arguments == {"query": "hello"}
        assert inv.trusted_context is ctx

    def test_tool_result_frozen(self) -> None:
        res = ToolResult(output="done", metadata={"status": "ok"})
        assert res.output == "done"
        assert res.metadata == {"status": "ok"}

    def test_tool_descriptor(self) -> None:
        desc = ToolDescriptor(key="web_search", description="Search the web")
        assert desc.key == "web_search"


class TestReservedKeys:
    def test_assert_model_arguments_trusted_free_ok(self) -> None:
        assert_model_arguments_trusted_free({"query": "hello", "max_results": 5})

    def test_assert_model_arguments_trusted_free_raises_on_reserved_key(self) -> None:
        with pytest.raises(ForbiddenTrustedFieldError) as exc_info:
            assert_model_arguments_trusted_free({"trusted_context": "evil"})
        assert exc_info.value.code == "forbidden_trusted_field"

    @pytest.mark.parametrize(
        "key",
        [
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
        ],
    )
    def test_assert_model_arguments_trusted_free_raises_on_all_reserved_keys(
        self, key: str
    ) -> None:
        with pytest.raises(ForbiddenTrustedFieldError) as exc_info:
            assert_model_arguments_trusted_free({key: "value"})
        assert exc_info.value.code == "forbidden_trusted_field"

    def test_assert_model_arguments_trusted_free_raises_on_nested_reserved_key(self) -> None:
        with pytest.raises(ForbiddenTrustedFieldError):
            assert_model_arguments_trusted_free({"params": {"arguments": {"user_id": "evil"}}})


class TestExtractTrustedContextFromHeaders:
    def test_minimal_headers(self) -> None:
        headers = {INTERNAL_AUTH_HEADER: "svc_token"}
        ctx = extract_trusted_context_from_headers(headers)
        assert ctx.user_id is None
        assert ctx.tenant_id is None
        assert ctx.binding_references == {}

    def test_full_identity_headers(self) -> None:
        headers = {
            INTERNAL_AUTH_HEADER: "svc_token",
            USER_ID_HEADER: "u123",
            TENANT_ID_HEADER: "t456",
            "x-project-id": "p789",
            "x-request-id": "r001",
            "x-attachment-handle-0": "att-1",
            f"{BINDING_REF_HEADER}-mail": "mbind_abc",
            f"{BINDING_REF_HEADER}-document": "dbind_xyz",
        }
        ctx = extract_trusted_context_from_headers(headers)
        assert ctx.user_id == "u123"
        assert ctx.tenant_id == "t456"
        assert ctx.project_id == "p789"
        assert ctx.request_id == "r001"
        assert ctx.attachment_handles == ("att-1",)
        assert ctx.binding_references == {
            "mail": "mbind_abc",
            "document": "dbind_xyz",
        }


class TestRedactPayload:
    def test_redact_dict_with_secret_key(self) -> None:
        payload = {
            "user_id": "u123",
            "token": "super_secret",
            "api_key": "key_xyz",
            "nested": {"password": "sekret"},
            f"{BINDING_REF_HEADER}-mail": "mbind_abc",
        }
        redacted = redact_payload(payload)
        assert redacted["user_id"] == "u123"
        assert redacted["token"] == "***REDACTED***"
        assert redacted["api_key"] == "***REDACTED***"
        assert redacted["nested"]["password"] == "***REDACTED***"
        assert redacted[f"{BINDING_REF_HEADER}-mail"] == "***REDACTED***"

    def test_redact_list(self) -> None:
        payload = [{"token": "a"}, {"token": "b"}]
        redacted = redact_payload(payload)
        assert redacted[0]["token"] == "***REDACTED***"
        assert redacted[1]["token"] == "***REDACTED***"

    def test_redact_primitive_passthrough(self) -> None:
        assert redact_payload("hello") == "hello"
        assert redact_payload(42) == 42
        assert redact_payload(None) is None

    def test_redact_trusted_context_key(self) -> None:
        payload = {"trusted_context": {"user_id": "u123"}}
        redacted = redact_payload(payload)
        assert redacted["trusted_context"] == "***REDACTED***"


class TestBuildTransportHeaders:
    def test_none_context_returns_only_internal_token(self) -> None:
        headers = build_transport_headers(None, "svc_token")
        assert headers == {INTERNAL_AUTH_HEADER: "svc_token"}

    def test_full_context(self) -> None:
        ctx = TrustedToolContext(
            user_id="u123",
            tenant_id="t456",
            project_id="p789",
            request_id="r001",
            binding_references={"mail": "mbind_abc"},
            attachment_handles=("att-1",),
        )
        headers = build_transport_headers(ctx, "svc_token")
        assert headers[INTERNAL_AUTH_HEADER] == "svc_token"
        assert headers[USER_ID_HEADER] == "u123"
        assert headers[TENANT_ID_HEADER] == "t456"
        assert headers["x-project-id"] == "p789"
        assert headers["x-request-id"] == "r001"
        assert headers["x-attachment-handle-0"] == "att-1"
        assert headers[f"{BINDING_REF_HEADER}-mail"] == "mbind_abc"


class TestValidateInvocation:
    def test_validate_invocation_ok(self) -> None:
        inv = ToolInvocation(model_arguments={"query": "hello"})
        validate_invocation(inv)

    def test_validate_invocation_rejects_reserved(self) -> None:
        inv = ToolInvocation(model_arguments={"trusted_context": "evil", "query": "hello"})
        with pytest.raises(ForbiddenTrustedFieldError):
            validate_invocation(inv)

    def test_invocation_and_trusted_context_copy_mapping_inputs(self) -> None:
        model_arguments = {"query": "hello"}
        binding_references = {"mail": "mbind_abc"}
        ctx = TrustedToolContext(binding_references=binding_references)
        inv = ToolInvocation(model_arguments=model_arguments, trusted_context=ctx)

        model_arguments["query"] = "changed"
        binding_references["mail"] = "changed"

        assert inv.model_arguments == {"query": "hello"}
        assert ctx.binding_references == {"mail": "mbind_abc"}


class TestContextVar:
    def test_set_and_get(self) -> None:
        ctx = TrustedToolContext(user_id="u123")
        set_current_trusted_context(ctx)
        assert get_current_trusted_context() is ctx

    def test_get_when_not_set(self) -> None:
        set_current_trusted_context(None)
        assert get_current_trusted_context() is None


class TestTrustedContextMiddleware:
    @pytest.fixture
    def app(self):
        async def endpoint(request: Request) -> JSONResponse:
            ctx = get_current_trusted_context()
            if request.url.path == "/secret":
                return JSONResponse(
                    {
                        "token": "secret",
                        "trusted_context": {"user_id": "u123"},
                        f"{BINDING_REF_HEADER}-mail": "mbind_abc",
                        "visible": "ok",
                    }
                )
            if ctx is None:
                return JSONResponse({"trusted": None})
            return JSONResponse(
                {
                    "trusted": {
                        "user_id": ctx.user_id,
                        "tenant_id": ctx.tenant_id,
                        "binding_refs": dict(ctx.binding_references),
                        "attachment_handles": ctx.attachment_handles,
                    }
                }
            )

        app = Starlette(
            middleware=[Middleware(TrustedContextMiddleware)],
            routes=[],
        )
        app.add_route("/check", endpoint, methods=["GET", "POST"])
        app.add_route("/secret", endpoint, methods=["POST"])
        return app

    def test_internal_request_extracts_trusted_context(self, app, monkeypatch) -> None:
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "valid_token")
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/check",
            headers={
                INTERNAL_AUTH_HEADER: "valid_token",
                USER_ID_HEADER: "u123",
                TENANT_ID_HEADER: "t456",
                "x-attachment-handle-0": "att-1",
                f"{BINDING_REF_HEADER}-mail": "mbind_abc",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["trusted"]["user_id"] == "u123"
        assert data["trusted"]["tenant_id"] == "t456"
        assert data["trusted"]["binding_refs"] == {"mail": "mbind_abc"}
        assert data["trusted"]["attachment_handles"] == ["att-1"]

    def test_non_internal_request_no_trusted_context(self, app) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/check")
        assert response.status_code == 200
        assert response.json()["trusted"] is None

    def test_request_with_reserved_key_in_body_rejected(self, app, monkeypatch) -> None:
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "valid_token")
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/check",
            headers={INTERNAL_AUTH_HEADER: "valid_token"},
            json={"trusted_context": "forged_value", "query": "hello"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "forbidden_trusted_field"

    def test_public_request_with_reserved_key_in_body_rejected(self, app) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/check", json={"trusted_context": "forged_value"})
        assert response.status_code == 400

    def test_json_rpc_arguments_with_reserved_key_rejected(self, app, monkeypatch) -> None:
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "valid_token")
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/check",
            headers={INTERNAL_AUTH_HEADER: "valid_token"},
            json={"params": {"arguments": {"trusted_context": "forged_value"}}},
        )
        assert response.status_code == 400

    def test_invalid_internal_token_does_not_trust_identity_headers(self, app, monkeypatch) -> None:
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "real_token")
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/check",
            headers={INTERNAL_AUTH_HEADER: "wrong", USER_ID_HEADER: "u123"},
        )
        assert response.status_code == 200
        assert response.json()["trusted"] is None

    def test_response_payload_is_redacted(self, app, monkeypatch) -> None:
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "valid_token")
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/secret",
            headers={INTERNAL_AUTH_HEADER: "valid_token"},
        )
        assert response.status_code == 200
        assert response.json() == {
            "token": "***REDACTED***",
            "trusted_context": "***REDACTED***",
            f"{BINDING_REF_HEADER}-mail": "***REDACTED***",
            "visible": "ok",
        }

    def test_trusted_context_cleared_after_request(self, app, monkeypatch) -> None:
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "valid_token")
        client = TestClient(app, raise_server_exceptions=False)
        client.post(
            "/check",
            headers={
                INTERNAL_AUTH_HEADER: "valid_token",
                USER_ID_HEADER: "u123",
            },
        )
        assert get_current_trusted_context() is None
