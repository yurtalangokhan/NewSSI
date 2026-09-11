from types import SimpleNamespace

from idempotency import IdempotencyMode

MUTATING_METHODS = {"DELETE", "PATCH", "POST", "PUT"}


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
    assert config.principal_extractor is not None


def test_rag_idempotency_policy_classifies_representative_routes() -> None:
    from langconnect.idempotency import (
        build_idempotency_exclude_paths,
        build_idempotency_policy,
    )

    policy = build_idempotency_policy(api_prefix="/api/v9")

    assert build_idempotency_exclude_paths(api_prefix="/api/v9") == {
        "/api/v9/health",
        "/api/v9/health/ready",
    }
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


def test_rag_idempotency_policy_enforces_all_domain_required_routes() -> None:
    """Guard test: every high-risk route must be DOMAIN_REQUIRED with key enforcement.

    This test exists to catch routes that fall through to the default
    (optional_replay) without being explicitly classified. Upload-jobs starts a
    background upload job and is high-risk, so it must require an idempotency key.
    """
    from langconnect.idempotency import build_idempotency_policy

    policy = build_idempotency_policy(api_prefix="/api/v9")

    for method, path in [
        # Graph build operations (high-risk: start background jobs)
        ("POST", "/api/v9/graph/build"),
        ("POST", "/api/v9/graph/build/collection-1/pause"),
        ("POST", "/api/v9/graph/build/collection-1/resume"),
        ("POST", "/api/v9/graph/build/collection-1/stop"),
        # Document operations
        ("POST", "/api/v9/collections/collection-1/documents"),
        # Upload jobs (high-risk: start background upload job, returns 202)
        (
            "POST",
            "/api/v9/collections/collection-1/documents/upload-jobs",
        ),
        # Destructive deletes
        ("DELETE", "/api/v9/graph/collections/collection-1"),
        ("DELETE", "/api/v9/collections/collection-1/force"),
    ]:
        resolved = policy.resolve(method, path)
        assert resolved.mode == IdempotencyMode.DOMAIN_REQUIRED, (
            f"Route {method} {path} must be DOMAIN_REQUIRED, got {resolved.mode}"
        )
        assert resolved.enforce_missing_key is True, (
            f"Route {method} {path} must enforce missing key"
        )


def test_rag_idempotency_policy_explicitly_maps_registered_mutating_routes() -> None:
    from fastapi.routing import APIRoute

    from langconnect.idempotency import build_idempotency_policy
    from langconnect.server import APP

    policy = build_idempotency_policy()

    unmapped = []
    for route in APP.routes:
        if not isinstance(route, APIRoute):
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
