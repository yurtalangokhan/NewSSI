from src.core.auth import _get_valid_api_keys
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
