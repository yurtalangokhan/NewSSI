from types import SimpleNamespace

from idempotency import IdempotencyMode


def test_tools_service_idempotency_config_uses_settings_values() -> None:
    from src.core.idempotency import build_idempotency_config

    settings = SimpleNamespace(
        REDIS_HOST="redis-host",
        REDIS_PORT=6380,
        REDIS_DB=2,
        REDIS_PASSWORD="test-secret",  # noqa: S106
        IDEMPOTENCY_TTL=120,
        IDEMPOTENCY_ENABLED=True,
        IDEMPOTENCY_ENFORCE_REQUIRED_KEYS=True,
        IDEMPOTENCY_LOCK_TTL=7,
        IDEMPOTENCY_WAIT_TIMEOUT=3.5,
    )

    config = build_idempotency_config(settings)

    assert config.redis_host == "redis-host"
    assert config.redis_port == 6380
    assert config.redis_db == 2
    assert config.redis_password == "test-secret"
    assert config.idempotency_ttl == 120
    assert config.enforce_required_keys is True
    assert config.lock_ttl == 7
    assert config.wait_timeout == 3.5
    assert config.service_name == "tools-service"
    assert config.principal_extractor is not None


def test_tools_service_idempotency_excludes_health_paths() -> None:
    from src.core.idempotency import build_idempotency_exclude_paths

    assert build_idempotency_exclude_paths() == {"/health", "/health/ready"}


def test_tools_service_mcp_route_requires_domain_classification_without_enforcing_key() -> None:
    """``/mcp`` must stay DOMAIN_REQUIRED but never 400 a missing key.

    MCP streamable-HTTP sessions issue many POSTs (initialize, tools/list,
    tools/call) sharing one connection's headers, so a single static
    Idempotency-Key cannot represent one logical operation. Requiring one
    would break every legitimate MCP client, including agent-service's
    MultiServerMCPClient.
    """
    from src.core.idempotency import build_idempotency_policy

    policy = build_idempotency_policy()
    resolved = policy.resolve("POST", "/mcp")

    assert resolved.mode == IdempotencyMode.DOMAIN_REQUIRED
    assert resolved.enforce_missing_key is False


def test_tools_service_idempotency_defaults_to_optional_replay() -> None:
    from src.core.idempotency import build_idempotency_policy

    policy = build_idempotency_policy()

    assert policy.default_mode == IdempotencyMode.OPTIONAL_REPLAY
