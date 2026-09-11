from types import SimpleNamespace

from idempotency import IdempotencyMode

MUTATING_METHODS = {"DELETE", "PATCH", "POST", "PUT"}


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
    assert config.principal_extractor is not None


def test_agent_idempotency_policy_classifies_representative_routes() -> None:
    from core.idempotency import build_idempotency_exclude_paths, build_idempotency_policy

    policy = build_idempotency_policy(api_prefix="/api/v9")

    assert build_idempotency_exclude_paths(api_prefix="/api/v9") == {
        "/api/v9/health",
        "/api/v9/health/ready",
        "/internal/connector-tools/resolve",
        "/api/v9/internal/connector-tools/resolve",
    }
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
    assert policy.resolve("DELETE", "/api/v9/admin/ollama/models/hf.co/bartowski/model").mode == (
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
        ("DELETE", "/api/v9/admin/ollama/models/hf.co/bartowski/model"),
    ]:
        resolved = policy.resolve(method, path)
        assert resolved.mode == IdempotencyMode.DOMAIN_REQUIRED
        assert resolved.enforce_missing_key is True


def test_agent_idempotency_policy_covers_rebased_side_effects() -> None:
    from core.idempotency import build_idempotency_policy

    policy = build_idempotency_policy(api_prefix="/api/v9")

    for method, path, expected_mode in [
        (
            "POST",
            "/api/v9/chat/create-chat-message-feedback",
            IdempotencyMode.DOMAIN_REQUIRED,
        ),
        (
            "PUT",
            "/api/v9/chat/update-chat-session-model",
            IdempotencyMode.OPTIONAL_REPLAY,
        ),
        (
            "PUT",
            "/api/v9/chat/update-chat-session-temperature",
            IdempotencyMode.OPTIONAL_REPLAY,
        ),
        ("POST", "/api/v9/providers", IdempotencyMode.REQUIRED_REPLAY),
        ("PUT", "/api/v9/providers/provider-1", IdempotencyMode.OPTIONAL_REPLAY),
        (
            "DELETE",
            "/api/v9/providers/provider-1",
            IdempotencyMode.OPTIONAL_REPLAY,
        ),
        (
            "POST",
            "/api/v9/datasources/source-1/schedule",
            IdempotencyMode.REQUIRED_REPLAY,
        ),
        (
            "PUT",
            "/api/v9/datasources/source-1/schedule",
            IdempotencyMode.REQUIRED_REPLAY,
        ),
        (
            "DELETE",
            "/api/v9/datasources/source-1/schedule",
            IdempotencyMode.REQUIRED_REPLAY,
        ),
        # Chat session management
        ("DELETE", "/api/v9/chat/sessions/session-1", IdempotencyMode.REQUIRED_REPLAY),
        ("DELETE", "/api/v9/chat/delete-chat-session/session-1", IdempotencyMode.REQUIRED_REPLAY),
        # Project operations
        ("DELETE", "/api/v9/user/projects/proj-1/files/file-1", IdempotencyMode.DOMAIN_REQUIRED),
        ("DELETE", "/api/v9/user/projects/file/file-1", IdempotencyMode.DOMAIN_REQUIRED),
        # Web search admin operations
        (
            "POST",
            "/api/v9/admin/web-search/content-providers/reset-default",
            IdempotencyMode.DOMAIN_REQUIRED,
        ),
        (
            "POST",
            "/api/v9/admin/web-search/content-providers/provider-1/activate",
            IdempotencyMode.DOMAIN_REQUIRED,
        ),
        (
            "POST",
            "/api/v9/admin/web-search/content-providers/provider-1/deactivate",
            IdempotencyMode.DOMAIN_REQUIRED,
        ),
        # MCP tool sync
        ("POST", "/api/v9/mcp-tools/sync", IdempotencyMode.DOMAIN_REQUIRED),
        ("POST", "/api/v9/mcp-tools/provider/provider-1/sync", IdempotencyMode.DOMAIN_REQUIRED),
        ("DELETE", "/api/v9/mcp-tools/tool-1", IdempotencyMode.DOMAIN_REQUIRED),
        # Datasource connector operations
        (
            "POST",
            "/api/v9/datasources/connectors/connector-1/validate",
            IdempotencyMode.DOMAIN_REQUIRED,
        ),
    ]:
        assert policy.resolve(method, path).mode == expected_mode


def test_agent_idempotency_policy_covers_admin_mcp_mutations() -> None:
    from core.idempotency import build_idempotency_policy

    policy = build_idempotency_policy(api_prefix="/api/v9")

    for method, path, expected_mode in [
        ("POST", "/api/v9/admin/mcp/server", IdempotencyMode.REQUIRED_REPLAY),
        (
            "POST",
            "/api/v9/admin/mcp/servers/create",
            IdempotencyMode.REQUIRED_REPLAY,
        ),
        (
            "PATCH",
            "/api/v9/admin/mcp/server/server-1",
            IdempotencyMode.OPTIONAL_REPLAY,
        ),
        (
            "PATCH",
            "/api/v9/admin/mcp/server/server-1/status",
            IdempotencyMode.OPTIONAL_REPLAY,
        ),
        (
            "DELETE",
            "/api/v9/admin/mcp/server/server-1",
            IdempotencyMode.REQUIRED_REPLAY,
        ),
        (
            "PATCH",
            "/api/v9/admin/tool/status",
            IdempotencyMode.OPTIONAL_REPLAY,
        ),
    ]:
        assert policy.resolve(method, path).mode == expected_mode


def test_agent_idempotency_policy_explicitly_maps_registered_mutating_routes() -> None:
    from fastapi.routing import APIRoute

    from app import app
    from core.idempotency import build_idempotency_exclude_paths, build_idempotency_policy

    policy = build_idempotency_policy()

    unmapped = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path in build_idempotency_exclude_paths():
            continue
        for method in route.methods or set():
            if method not in MUTATING_METHODS:
                continue
            has_exact_policy = any(
                candidate.method == method and candidate.path == route.path
                for candidate in policy.route_policies
            )
            if not has_exact_policy:
                unmapped.append(f"{method} {route.path}")

    assert unmapped == []
