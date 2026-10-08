"""Secret getters use the same central environment source as every other setting."""

import pytest
from config_manager import env


def _set_required(monkeypatch):
    for name, value in {
        "MCP_HOST": "0.0.0.0",
        "TOOLS_SERVICE_PORT": "8003",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_TOOL_SERVICE_USER": "tools",
        "POSTGRES_TOOL_SERVICE_DB": "tools",
        "INTERNAL_USER_SERVICE_URL": "http://apisix:8000/internal/user-service",
    }.items():
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("INTERNAL_SERVICE_TOKEN", "internal-secret"),
        ("POSTGRES_TOOL_SERVICE_PASSWORD", "postgres-secret"),
        ("REDIS_PASSWORD", "redis-secret"),
    ],
)
def test_secret_getters_return_environment_value(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    assert getattr(env, name) == value


def test_secret_getter_reflects_environment_changes(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
    assert env.INTERNAL_SERVICE_TOKEN == "first"
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
    assert env.INTERNAL_SERVICE_TOKEN == "second"


def test_missing_required_password_raises(monkeypatch):
    _set_required(monkeypatch)
    monkeypatch.delenv("POSTGRES_TOOL_SERVICE_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="POSTGRES_TOOL_SERVICE_PASSWORD"):
        env.validate_tools_service()
