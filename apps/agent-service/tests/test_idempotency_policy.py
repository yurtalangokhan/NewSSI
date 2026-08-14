from types import SimpleNamespace

from idempotency import IdempotencyMode


def test_agent_idempotency_config_uses_settings_values() -> None:
    from core.idempotency import build_idempotency_config

    settings = SimpleNamespace(
        REDIS_HOST="redis-host",
        REDIS_PORT=6380,
        REDIS_DB=2,
        REDIS_PASSWORD="secret",
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
    assert config.redis_password == "secret"
    assert config.idempotency_ttl == 120
    assert config.enforce_required_keys is True
    assert config.lock_ttl == 7
    assert config.wait_timeout == 3.5
    assert config.service_name == "agent-service"


def test_agent_idempotency_policy_classifies_representative_routes() -> None:
    from core.idempotency import build_idempotency_exclude_paths, build_idempotency_policy

    policy = build_idempotency_policy(api_prefix="/api/v9")

    assert build_idempotency_exclude_paths(api_prefix="/api/v9") == {"/api/v9/health"}
    assert (
        policy.resolve("POST", "/api/v9/chat/send-chat-message").mode
        == IdempotencyMode.DOMAIN_REQUIRED
    )
    assert (
        policy.resolve("POST", "/api/v9/chat/create-chat-session").mode
        == IdempotencyMode.REQUIRED_REPLAY
    )
    assert (
        policy.resolve("PATCH", "/api/v9/chat/rename-chat-session").mode
        == IdempotencyMode.OPTIONAL_REPLAY
    )


def test_agent_idempotency_policy_classifies_spec_named_domain_routes() -> None:
    from core.idempotency import build_idempotency_policy

    policy = build_idempotency_policy(api_prefix="/api/v9")

    assert policy.resolve("POST", "/api/v9/ingest/batch").mode == (IdempotencyMode.DOMAIN_REQUIRED)
    assert policy.resolve("POST", "/api/v9/admin/web-search/content-providers/crawl").mode == (
        IdempotencyMode.DOMAIN_REQUIRED
    )
    assert policy.resolve("DELETE", "/api/v9/admin/ollama/models/llama3.2").mode == (
        IdempotencyMode.DOMAIN_REQUIRED
    )


def test_agent_idempotency_policy_enforces_ready_domain_routes() -> None:
    from core.idempotency import build_idempotency_policy

    policy = build_idempotency_policy(api_prefix="/api/v9")

    for method, path in [
        ("POST", "/api/v9/chat/send-chat-message"),
        ("POST", "/api/v9/chat/messages"),
        ("POST", "/api/v9/threads/thread-1/runs/stream"),
        ("POST", "/api/v9/agents/invoke"),
        ("POST", "/api/v9/agents/agent-1/invoke"),
        ("POST", "/api/v9/agents/stream"),
        ("POST", "/api/v9/agents/agent-1/stream"),
        ("POST", "/api/v9/proxy/mcp/execute"),
        ("POST", "/api/v9/datasources/source-1/sync"),
        ("POST", "/api/v9/ingest/batch"),
        ("POST", "/api/v9/user/projects/file/upload"),
        ("POST", "/api/v9/mail-configs/mail-1/test"),
        ("POST", "/api/v9/mail-configs/mail-1/send"),
        ("POST", "/api/v9/admin/providers/provider-1/sync-models"),
        ("POST", "/api/v9/admin/ollama/pull"),
        ("POST", "/api/v9/admin/web-search/content-providers/crawl"),
        ("POST", "/api/v9/admin/persona/upload-image"),
        ("DELETE", "/api/v9/admin/ollama/models/llama3.2"),
    ]:
        resolved = policy.resolve(method, path)
        assert resolved.mode == IdempotencyMode.DOMAIN_REQUIRED
        assert resolved.enforce_missing_key is True
