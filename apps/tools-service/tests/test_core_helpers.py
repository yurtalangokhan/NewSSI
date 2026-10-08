import json

import httpx
import pytest
from config_manager import env
from localization.core import set_locale

from src.core.authorization import authorize_binding_reference, get_user_service_permissions
from src.core.base import BaseToolCategory


def test_settings_reads_runtime_values_from_environment(monkeypatch):
    monkeypatch.setenv("MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("TOOLS_SERVICE_PORT", "9000")
    monkeypatch.setenv("USER_SERVICE_URL", "http://public/user-service")
    monkeypatch.setenv("INTERNAL_USER_SERVICE_URL", "http://gateway/internal/user-service/")
    monkeypatch.setenv("AGENT_SERVICE_URL", "http://public/agent-service")
    monkeypatch.setenv(
        "INTERNAL_AGENT_SERVICE_URL", "http://gateway/internal/agent-service/api/v1/"
    )
    monkeypatch.setenv("RAG_SERVICE_API_URL", "http://public/rag-service")
    monkeypatch.setenv("INTERNAL_RAG_SERVICE_API_URL", "http://gateway/internal/rag-service")
    monkeypatch.setenv("MCP_PUBLIC_BASE_URL", "http://public/tools-service/mcp")
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_TOOL_SERVICE_USER", "tools")
    monkeypatch.setenv("POSTGRES_TOOL_SERVICE_PASSWORD", "secret")
    monkeypatch.setenv("POSTGRES_TOOL_SERVICE_DB", "tools")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = env
    settings.validate_tools_service()

    assert settings.MCP_HOST == "127.0.0.1"
    assert settings.TOOLS_SERVICE_PORT == 9000
    assert settings.INTERNAL_USER_SERVICE_URL == "http://gateway/internal/user-service"
    assert settings.INTERNAL_AGENT_SERVICE_URL == "http://gateway/internal/agent-service/api/v1"
    assert settings.INTERNAL_RAG_SERVICE_API_URL == "http://gateway/internal/rag-service"
    assert settings.MCP_PUBLIC_BASE_URL == "http://public/tools-service/mcp"
    assert settings.tool_postgres_config == {
        "user": "tools",
        "password": "secret",
        "host": "postgres",
        "port": 5432,
        "database": "tools",
    }
    assert settings.LOG_LEVEL == "DEBUG"


def test_settings_rejects_public_user_url_without_internal_url(monkeypatch):
    monkeypatch.setenv("POSTGRES_TOOL_SERVICE_PASSWORD", "synthetic-password")
    monkeypatch.setenv("USER_SERVICE_URL", "http://public/user-service")
    monkeypatch.delenv("INTERNAL_USER_SERVICE_URL", raising=False)

    with pytest.raises(ValueError, match="INTERNAL_USER_SERVICE_URL"):
        env.validate_tools_service()


def test_optional_internal_clients_do_not_fall_back_to_web_urls(monkeypatch):
    monkeypatch.setenv("POSTGRES_TOOL_SERVICE_PASSWORD", "synthetic-password")
    monkeypatch.setenv("AGENT_SERVICE_URL", "http://public/agent-service")
    monkeypatch.setenv("RAG_SERVICE_API_URL", "http://public/rag-service")
    monkeypatch.delenv("INTERNAL_AGENT_SERVICE_URL", raising=False)
    monkeypatch.delenv("INTERNAL_RAG_SERVICE_API_URL", raising=False)
    monkeypatch.delenv("INTERNAL_RAG_API_URL", raising=False)

    settings = env

    assert settings.INTERNAL_AGENT_SERVICE_URL is None
    assert settings.INTERNAL_RAG_SERVICE_API_URL is None


def test_settings_raises_clear_error_for_missing_required_env(monkeypatch):
    for key in env.TOOLS_REQUIRED_KEYS:
        monkeypatch.delenv(key, raising=False)

    try:
        env.validate_tools_service()
    except ValueError as exc:
        assert "Required environment variable MCP_HOST is not set" in str(exc)
    else:
        raise AssertionError("env should reject missing required environment values")


def test_parse_json_param_returns_empty_dict_for_missing_or_invalid_input():
    assert BaseToolCategory.parse_json_param(None) == {}
    assert BaseToolCategory.parse_json_param("not-json") == {}


def test_parse_json_param_returns_decoded_dict():
    assert BaseToolCategory.parse_json_param('{"name": "tools"}') == {"name": "tools"}


def test_error_response_translates_key_with_interpolation():
    result = json.loads(BaseToolCategory.error_response("pdf.file_not_found", file_path="a.pdf"))
    assert result == {"success": False, "error": "File not found: a.pdf"}


def test_error_response_honors_current_locale():
    set_locale("tr")
    try:
        result = json.loads(
            BaseToolCategory.error_response("pdf.file_not_found", file_path="a.pdf")
        )
    finally:
        set_locale("en")
    assert result == {"success": False, "error": "Dosya bulunamadı: a.pdf"}


class _PermissionResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        # user-service answers in the shared response envelope.
        return {
            "statusCode": 200,
            "message": None,
            "data": {"permissions": ["tool:execute"]},
            "error": None,
        }


class _AsyncClient:
    captured_url: str = ""
    captured_headers: dict[str, str] = {}

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        return None

    async def get(self, url: str, **kwargs):
        self.__class__.captured_url = url
        self.__class__.captured_headers = kwargs.get("headers", {})
        return _PermissionResponse()


async def test_get_user_service_permissions_uses_api_v1_internal_path(
    monkeypatch,
):
    monkeypatch.setattr(
        "src.core.authorization._user_service_base_url",
        lambda: "http://apisix:8000/internal/user-service",
    )
    monkeypatch.setattr(
        "src.core.authorization.env",
        type(
            "Settings",
            (),
            {
                "INTERNAL_USER_SERVICE_URL": "http://apisix:8000/internal/user-service",
                "USER_PERMISSION_CACHE_TTL_SECONDS": 30.0,
                "INTERNAL_SERVICE_TOKEN": "internal-token",
            },
        )(),
    )
    monkeypatch.setattr("src.core.authorization._permission_cache_ttl", lambda: 30.0)
    monkeypatch.setattr("src.core.authorization.httpx.AsyncClient", _AsyncClient)

    assert await get_user_service_permissions("token", "user-1") == ["tool:execute"]
    assert (
        _AsyncClient.captured_url
        == "http://apisix:8000/internal/user-service/api/v1/internal/users/user-1/permissions"
    )
    assert _AsyncClient.captured_headers["X-Internal-Service-Token"] == "internal-token"


class _BindingDeniedResponse:
    status_code = 500


class _BindingErrorClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        return None

    async def get(self, url: str, **kwargs):
        return _BindingDeniedResponse()


class _BindingNetworkErrorClient(_BindingErrorClient):
    async def get(self, url: str, **kwargs):
        raise httpx.ConnectError("user-service down")


async def test_authorize_binding_reference_fails_closed_on_unexpected_status(
    monkeypatch,
):
    monkeypatch.setattr(
        "src.core.authorization._user_service_base_url",
        lambda: "http://user-service",
    )
    monkeypatch.setattr(
        "src.core.authorization.env",
        type("Settings", (), {"INTERNAL_SERVICE_TOKEN": "internal-token"})(),
    )
    monkeypatch.setattr("src.core.authorization.httpx.AsyncClient", _BindingErrorClient)

    result = await authorize_binding_reference(
        binding_type="mail",
        binding_id="ref-1",
        user_id="user-1",
        tenant_id=None,
        internal_token="internal-token",
    )

    assert result.authorized is False
    assert result.reason == "Authorization check returned unexpected status."


async def test_authorize_binding_reference_fails_closed_when_user_service_unavailable(
    monkeypatch,
):
    monkeypatch.setattr(
        "src.core.authorization._user_service_base_url",
        lambda: "http://user-service",
    )
    monkeypatch.setattr(
        "src.core.authorization.env",
        type("Settings", (), {"INTERNAL_SERVICE_TOKEN": "internal-token"})(),
    )
    monkeypatch.setattr("src.core.authorization.httpx.AsyncClient", _BindingNetworkErrorClient)

    result = await authorize_binding_reference(
        binding_type="mail",
        binding_id="ref-1",
        user_id="user-1",
        tenant_id=None,
        internal_token="internal-token",
    )

    assert result.authorized is False
    assert result.reason == "Authorization check unavailable."
