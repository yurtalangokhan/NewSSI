from types import SimpleNamespace

from idempotency import IdempotencyMode


def test_rag_idempotency_config_uses_settings_values() -> None:
    from langconnect.idempotency import build_idempotency_config

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
    assert config.service_name == "rag-service"


def test_rag_idempotency_policy_classifies_representative_routes() -> None:
    from langconnect.idempotency import (
        build_idempotency_exclude_paths,
        build_idempotency_policy,
    )

    policy = build_idempotency_policy(api_prefix="/api/v9")

    assert build_idempotency_exclude_paths(api_prefix="/api/v9") == {"/api/v9/health"}
    graph_build_policy = policy.resolve("POST", "/api/v9/graph/build")
    assert graph_build_policy.mode == IdempotencyMode.DOMAIN_REQUIRED
    assert graph_build_policy.enforce_missing_key is True
    assert policy.resolve("POST", "/api/v9/collections").mode == (
        IdempotencyMode.REQUIRED_REPLAY
    )
    assert policy.resolve("POST", "/api/v9/graph/search").mode == (
        IdempotencyMode.OPTIONAL_REPLAY
    )


def test_rag_idempotency_policy_classifies_spec_named_routes() -> None:
    from langconnect.idempotency import build_idempotency_policy

    policy = build_idempotency_policy(api_prefix="/api/v9")

    for method, path in [
        ("DELETE", "/api/v9/graph/collections/collection-1"),
        ("DELETE", "/api/v9/collections/collection-1/force"),
    ]:
        resolved = policy.resolve(method, path)
        assert resolved.mode == IdempotencyMode.DOMAIN_REQUIRED
        assert resolved.enforce_missing_key is True

    assert policy.resolve("PATCH", "/api/v9/collections/collection-1").mode == (
        IdempotencyMode.REQUIRED_REPLAY
    )
    assert policy.resolve("POST", "/api/v9/graph/cypher").mode == (
        IdempotencyMode.OPTIONAL_REPLAY
    )
