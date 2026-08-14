from types import SimpleNamespace

from idempotency import IdempotencyMode


def test_user_idempotency_config_uses_settings_values() -> None:
    from src.core.idempotency import build_idempotency_config

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
    assert config.service_name == "user-service"


def test_user_idempotency_policy_classifies_representative_routes() -> None:
    from src.core.idempotency import build_idempotency_exclude_paths, build_idempotency_policy

    policy = build_idempotency_policy(api_prefix="/api/v9")

    assert build_idempotency_exclude_paths(api_prefix="/api/v9") == {
        "/api/v9/health",
        "/api/v9/health/",
        "/api/v9/health/ready",
    }
    assert policy.resolve("POST", "/api/v9/auth/login").mode == IdempotencyMode.EXCLUDED
    invite_policy = policy.resolve("POST", "/api/v9/users/invite")
    assert invite_policy.mode == IdempotencyMode.DOMAIN_REQUIRED
    assert invite_policy.enforce_missing_key is True
    assert policy.resolve("POST", "/api/v9/users/me/memories/").mode == (
        IdempotencyMode.REQUIRED_REPLAY
    )
    assert policy.resolve("PATCH", "/api/v9/users/me/settings/").mode == (
        IdempotencyMode.OPTIONAL_REPLAY
    )


def test_user_idempotency_policy_classifies_spec_named_domain_routes() -> None:
    from src.core.idempotency import build_idempotency_policy

    policy = build_idempotency_policy(api_prefix="/api/v9")

    for path in [
        "/api/v9/auth/sync-users",
        "/api/v9/users/me/api-keys/",
    ]:
        resolved = policy.resolve("POST", path)
        assert resolved.mode == IdempotencyMode.DOMAIN_REQUIRED
        assert resolved.enforce_missing_key is True


def test_user_idempotency_policy_covers_rebased_mutations() -> None:
    from src.core.idempotency import build_idempotency_policy

    policy = build_idempotency_policy(api_prefix="/api/v9")

    for method, path, expected_mode in [
        ("POST", "/api/v9/roles/", IdempotencyMode.REQUIRED_REPLAY),
        ("POST", "/api/v9/coarse-roles/", IdempotencyMode.REQUIRED_REPLAY),
        ("POST", "/api/v9/organizations", IdempotencyMode.REQUIRED_REPLAY),
        (
            "POST",
            "/api/v9/organizations/org-1/users",
            IdempotencyMode.REQUIRED_REPLAY,
        ),
        (
            "POST",
            "/api/v9/organizations/org-1/users/bulk",
            IdempotencyMode.REQUIRED_REPLAY,
        ),
        (
            "PUT",
            "/api/v9/roles/admin/permissions",
            IdempotencyMode.REQUIRED_REPLAY,
        ),
        ("POST", "/api/v9/permissions/sync", IdempotencyMode.DOMAIN_REQUIRED),
    ]:
        assert policy.resolve(method, path).mode == expected_mode
