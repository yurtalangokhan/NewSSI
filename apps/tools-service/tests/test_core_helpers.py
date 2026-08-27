import json

import httpx
from i18n.core import set_locale

from src.core.auth import _get_valid_api_keys
from src.core.authorization import authorize_binding_reference, get_user_service_permissions
from src.core.base import BaseToolCategory
from src.core.settings import Settings


def test_get_valid_api_keys_trims_and_drops_empty_values(monkeypatch):
    monkeypatch.setenv("VALID_API_KEYS", " alpha, , beta ,")

    assert _get_valid_api_keys() == {"alpha", "beta"}


def test_settings_reads_runtime_values_from_environment(monkeypatch):
    monkeypatch.setenv("MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("MCP_PORT", "9000")
    monkeypatch.setenv("USER_SERVICE_URL", "http://user-service")
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_USER", "tools")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("POSTGRES_DB", "tools")

    settings = Settings.from_env()

    assert settings.mcp_host == "127.0.0.1"
    assert settings.mcp_port == 9000
    assert settings.user_service_url == "http://user-service"
    assert settings.postgres_config == {
        "user": "tools",
        "password": "secret",
        "host": "postgres",
        "port": 5432,
        "database": "tools",
    }


def test_settings_raises_clear_error_for_missing_required_env(monkeypatch):
    for key in Settings.required_env_names():
        monkeypatch.delenv(key, raising=False)

    try:
        Settings.from_env()
    except ValueError as exc:
        assert "Required environment variable MCP_HOST is not set" in str(exc)
    else:
        raise AssertionError("Settings.from_env() should reject missing required env")


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
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, list[str]]:
        return {"permissions": ["tool:execute"]}


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
        lambda: "http://kong:8000/internal/user-service",
    )
    monkeypatch.setattr(
        "src.core.authorization.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "user_service_url": "http://kong:8000/internal/user-service",
                "user_permission_cache_ttl_seconds": 30.0,
                "internal_service_token": "internal-token",
            },
        )(),
    )
    monkeypatch.setattr("src.core.authorization._permission_cache_ttl", lambda: 30.0)
    monkeypatch.setattr("src.core.authorization.httpx.AsyncClient", _AsyncClient)

    assert await get_user_service_permissions("token", "user-1") == ["tool:execute"]
    assert (
        _AsyncClient.captured_url
        == "http://kong:8000/internal/user-service/api/v1/internal/users/user-1/permissions"
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
        "src.core.authorization.get_settings",
        lambda: type("Settings", (), {"internal_service_token": "internal-token"})(),
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
        "src.core.authorization.get_settings",
        lambda: type("Settings", (), {"internal_service_token": "internal-token"})(),
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
