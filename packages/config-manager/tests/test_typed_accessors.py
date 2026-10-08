"""The shared accessor owns parsing for backend configuration values."""

import os
from unittest.mock import patch

import pytest

from config_manager import ConfigManager, env


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("AGENT_RECURSION_LIMIT", "42", 42),
        ("LLM_REQUEST_TIMEOUT", "12.5", 12.5),
        ("POSTGRES_POOL_USE_LIFO", "false", False),
        ("IDEMPOTENCY_TTL", "120", 120),
        ("REDIS_PORT", "6380", 6380),
        ("COOKIE_SECURE", "true", True),
    ],
)
def test_backend_values_are_typed(monkeypatch, name, value, expected):
    monkeypatch.setenv(name, value)
    assert getattr(env, name) == expected


def test_backend_defaults_and_optional_values(monkeypatch):
    monkeypatch.delenv("LLM_REQUEST_TIMEOUT", raising=False)
    monkeypatch.delenv("INTERNAL_TOOLS_SERVICE_URL", raising=False)
    assert env.LLM_REQUEST_TIMEOUT == 600.0
    assert env.INTERNAL_TOOLS_SERVICE_URL is None


def test_service_port_does_not_read_legacy_alias(monkeypatch):
    monkeypatch.setenv("PORT", "9999")
    monkeypatch.delenv("AGENT_SERVICE_PORT", raising=False)
    assert env.AGENT_SERVICE_PORT == 8080


def test_auth_and_encryption_keys_do_not_read_legacy_aliases(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", "legacy-auth")
    monkeypatch.setenv("ENCRYPTION_KEY", "legacy-encryption")
    monkeypatch.delenv("AUTHENTICATION_SECRET", raising=False)
    monkeypatch.delenv("LLM_PROVIDER_API_ENCRYPTION_KEY", raising=False)
    assert env.AUTHENTICATION_SECRET is None
    assert env.LLM_PROVIDER_API_ENCRYPTION_KEY is None


def test_unknown_getter_is_rejected():
    with pytest.raises(AttributeError):
        _ = env.NOT_A_CONFIGURED_KEY


def test_optional_mcp_allowlist_is_parsed_by_accessor(monkeypatch):
    monkeypatch.setenv("MCP_URL_ALLOWLIST", '["https://one.example/mcp", "https://two.example/mcp"]')
    assert env.MCP_URL_ALLOWLIST == (
        "https://one.example/mcp",
        "https://two.example/mcp",
    )


def test_agent_derived_values_and_defaults():
    with patch.dict(os.environ, {}, clear=True):
        settings = ConfigManager()
        assert settings.HOST == "0.0.0.0"
        assert settings.AGENT_SERVICE_PORT == 8080
        assert settings.DEFAULT_MODEL == "llama3.1:8b"
        assert {"llama3.1:8b"} == settings.AVAILABLE_MODELS
        assert settings.BASE_URL == "http://0.0.0.0:8080"
        assert settings.CORS_ALLOWED_ORIGINS == "http://localhost:3000"
        assert settings.cors_origins == ["http://localhost:3000", "http://localhost:8123"]
        assert settings.agent_log_level == "WARNING"
        assert settings.LOG_FORMAT == "text"
        assert not settings.is_dev()


def test_agent_derived_values_use_canonical_environment(monkeypatch):
    monkeypatch.setenv("DEFAULT_MODEL", "qwen3")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    monkeypatch.setenv("COMPATIBLE_MODEL", "custom")
    monkeypatch.setenv("AGENT_SERVICE_PORT", "8111")
    monkeypatch.setenv("MODE", "dev")
    assert {"qwen3", "llama3", "custom"} == env.AVAILABLE_MODELS
    assert env.BASE_URL.endswith(":8111")
    assert env.is_dev()


@pytest.mark.parametrize(
    "name",
    [
        "NEO4J_PASSWORD",
        "MILVUS_PASSWORD",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "REDIS_PASSWORD",
        "LLM_PROVIDER_API_ENCRYPTION_KEY",
        "MCP_CREDENTIAL_ENCRYPTION_KEY",
        "MCP_OAUTH_ENCRYPTION_KEY",
        "MAIL_CONFIG_ENCRYPTION_KEY",
        "USER_API_KEY_ENCRYPTION_KEY",
        "SYSTEM_SETTINGS_ENCRYPTION_KEY",
        "CONNECTOR_CONFIG_ENCRYPTION_KEY",
        "OPENAI_API_KEY",
        "POSTGRES_RAG_SERVICE_PASSWORD",
    ],
)
def test_credentials_have_no_default(name):
    with patch.dict(os.environ, {}, clear=True):
        assert not getattr(ConfigManager(), name)


def test_invalid_numeric_and_boolean_values_raise(monkeypatch):
    monkeypatch.setenv("AGENT_RECURSION_LIMIT", "many")
    with pytest.raises(ValueError, match="AGENT_RECURSION_LIMIT"):
        _ = env.AGENT_RECURSION_LIMIT
    monkeypatch.setenv("COOKIE_SECURE", "perhaps")
    with pytest.raises(ValueError, match="COOKIE_SECURE"):
        _ = env.COOKIE_SECURE


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("KEYCLOAK_JWKS_CACHE_TTL_SECONDS", "60", 60),
        ("LTM_CONTEXT_MAX_CHARS", "4000", 4000),
        ("LTM_EXTRACTION_WINDOW_MESSAGES", "8", 8),
        ("LTM_EXTRACTION_TIMEOUT_SECONDS", "12.5", 12.5),
        ("LTM_MAX_CONCURRENT_EXTRACTIONS", "3", 3),
        ("MEMORY_EXTRACTION_MODEL", "qwen3:8b", "qwen3:8b"),
        ("MEMORY_MAX_FACTS", "75", 75),
        ("POSTGRES_POOL_RECONNECT_TIMEOUT_SECONDS", "90", 90.0),
        ("PRODUCTION_RETENTION_DAYS", "14", 14),
        ("RAG_HTTP_TIMEOUT_SECONDS", "42.5", 42.5),
    ],
)
def test_memory_and_runtime_tunables_are_typed(monkeypatch, name, value, expected):
    monkeypatch.setenv(name, value)
    assert getattr(env, name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("KEYCLOAK_JWKS_CACHE_TTL_SECONDS", 300),
        ("LTM_CONTEXT_MAX_CHARS", 6000),
        ("LTM_EXTRACTION_WINDOW_MESSAGES", 6),
        ("LTM_EXTRACTION_TIMEOUT_SECONDS", 30.0),
        ("LTM_MAX_CONCURRENT_EXTRACTIONS", 5),
        # Unset means "extract with the conversation's own model".
        ("MEMORY_EXTRACTION_MODEL", None),
        ("MEMORY_MAX_FACTS", 50),
        ("POSTGRES_POOL_RECONNECT_TIMEOUT_SECONDS", 300.0),
        # Deleting real chat history is opt-in, not a shipped default.
        ("PRODUCTION_RETENTION_DAYS", 0),
        # Unset defers to configs/resilience.yaml in agent-service.
        ("RAG_HTTP_TIMEOUT_SECONDS", None),
    ],
)
def test_memory_and_runtime_tunable_defaults(monkeypatch, name, expected):
    monkeypatch.delenv(name, raising=False)
    assert getattr(env, name) == expected


def test_connector_sync_timeout_defaults_to_a_day_and_zero_turns_it_off(monkeypatch):
    monkeypatch.delenv("CONNECTOR_SYNC_TIMEOUT_SECONDS", raising=False)
    assert env.CONNECTOR_SYNC_TIMEOUT_SECONDS == 86400.0
    # An empty value is "not set", not "no limit".
    monkeypatch.setenv("CONNECTOR_SYNC_TIMEOUT_SECONDS", "")
    assert env.CONNECTOR_SYNC_TIMEOUT_SECONDS == 86400.0
    monkeypatch.setenv("CONNECTOR_SYNC_TIMEOUT_SECONDS", "1800")
    assert env.CONNECTOR_SYNC_TIMEOUT_SECONDS == 1800.0
    monkeypatch.setenv("CONNECTOR_SYNC_TIMEOUT_SECONDS", "0")
    assert env.CONNECTOR_SYNC_TIMEOUT_SECONDS is None


def test_blank_memory_extraction_model_means_unset(monkeypatch):
    monkeypatch.setenv("MEMORY_EXTRACTION_MODEL", "   ")
    assert env.MEMORY_EXTRACTION_MODEL is None


@pytest.mark.parametrize(
    "name",
    [
        "MCP_CREDENTIAL_ENCRYPTION_KEY",
        "MCP_OAUTH_ENCRYPTION_KEY",
        "MAIL_CONFIG_ENCRYPTION_KEY",
        "USER_API_KEY_ENCRYPTION_KEY",
        "SYSTEM_SETTINGS_ENCRYPTION_KEY",
        "CONNECTOR_CONFIG_ENCRYPTION_KEY",
    ],
)
def test_scope_encryption_keys_are_read_from_their_own_names(monkeypatch, name):
    monkeypatch.setenv(name, "scope-key")
    assert getattr(env, name) == "scope-key"


def test_scope_encryption_keys_ignore_the_superseded_shared_name(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "shared")
    monkeypatch.delenv("MAIL_CONFIG_ENCRYPTION_KEY", raising=False)
    assert env.MAIL_CONFIG_ENCRYPTION_KEY is None


def test_legacy_encryption_key_is_not_a_configured_getter(monkeypatch):
    monkeypatch.setenv("LEGACY_ENCRYPTION_KEY", "retired")
    with pytest.raises(AttributeError):
        _ = env.LEGACY_ENCRYPTION_KEY

_CHAT_RUN_DEFAULTS = {
    "CHAT_RUN_REPLAY_TTL_SECONDS": 600,
    "CHAT_RUN_LEASE_TTL_SECONDS": 10.0,
    "CHAT_RUN_HEARTBEAT_SECONDS": 2.0,
    "CHAT_RUN_MAX_EVENTS": 50000,
    "CHAT_RUN_CANCEL_GRACE_SECONDS": 5.0,
    "CHAT_RUN_SHUTDOWN_GRACE_SECONDS": 20.0,
    "CHAT_RUN_REAPER_INTERVAL_SECONDS": 10.0,
    "CHAT_RUN_MAX_DURATION_SECONDS": 3600,
}


def test_chat_run_settings_have_typed_defaults(monkeypatch):
    for name in _CHAT_RUN_DEFAULTS:
        monkeypatch.delenv(name, raising=False)
    for name, expected in _CHAT_RUN_DEFAULTS.items():
        assert getattr(env, name) == expected, name


def test_chat_run_settings_parse_overrides(monkeypatch):
    monkeypatch.setenv("CHAT_RUN_REPLAY_TTL_SECONDS", "900")
    monkeypatch.setenv("CHAT_RUN_HEARTBEAT_SECONDS", "0.5")
    assert env.CHAT_RUN_REPLAY_TTL_SECONDS == 900
    assert env.CHAT_RUN_HEARTBEAT_SECONDS == 0.5


def test_chat_run_settings_reject_non_numbers(monkeypatch):
    monkeypatch.setenv("CHAT_RUN_MAX_EVENTS", "many")
    with pytest.raises(ValueError, match="CHAT_RUN_MAX_EVENTS"):
        _ = env.CHAT_RUN_MAX_EVENTS


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("MERMAID_RENDER_TIMEOUT_SECONDS", "2.5", 2.5),
        ("MERMAID_RENDER_WORKERS", "3", 3),
        ("MERMAID_MAX_SOURCE_CHARS", "4000", 4000),
        ("DOCUMENT_DIAGRAM_CACHE_SIZE", "64", 64),
    ],
)
def test_diagram_rendering_tunables_are_typed(monkeypatch, name, value, expected):
    monkeypatch.setenv(name, value)
    assert getattr(env, name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("MERMAID_RENDER_TIMEOUT_SECONDS", 10.0),
        ("MERMAID_RENDER_WORKERS", 1),
        ("MERMAID_MAX_SOURCE_CHARS", 20000),
        ("DOCUMENT_DIAGRAM_CACHE_SIZE", 256),
    ],
)
def test_diagram_rendering_tunable_defaults(monkeypatch, name, expected):
    monkeypatch.delenv(name, raising=False)
    assert getattr(env, name) == expected
