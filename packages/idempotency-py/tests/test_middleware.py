from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import pytest
import redis.exceptions
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse

from idempotency import AsyncRedisPool, CachedResponse, IdempotencyConfig, IdempotencyMiddleware
from idempotency.models import IdempotencyMode, IdempotencyPolicy, IdempotencyPolicyConfig
from idempotency.storage import release_lock, renew_lock


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}
        self.set_calls: list[tuple[str, str, bool, int | None]] = []
        self.expire_calls: list[tuple[str, int]] = []
        self.eval_calls: list[tuple[str, tuple[Any, ...]]] = []

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.expirations[key] = ttl

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
        self.set_calls.append((key, value, nx, ex))
        if nx and key in self.values:
            return False
        self.values[key] = value
        if ex is not None:
            self.expirations[key] = ex
        return True

    async def expire(self, key: str, ttl: int) -> None:
        self.expire_calls.append((key, ttl))
        self.expirations[key] = ttl

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> int:
        self.eval_calls.append((script, keys_and_args))
        key = keys_and_args[0]
        token = keys_and_args[1]
        if self.values.get(key) == token:
            self.values.pop(key, None)
            return 1
        return 0


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    redis = FakeRedis()

    async def connect(config: IdempotencyConfig) -> FakeRedis:
        return redis

    monkeypatch.setattr(AsyncRedisPool, "connect", connect)
    return redis


def make_client(
    *,
    policy: IdempotencyPolicyConfig | None = None,
    cache_status: int = 200,
    stream: bool = False,
    enforce_required_keys: bool = True,
    max_cache_body_size: int = 1_048_576,
) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        IdempotencyMiddleware,
        config=IdempotencyConfig(
            redis_host="localhost",
            redis_port=6379,
            redis_db=0,
            redis_password="",
            idempotency_ttl=60,
            idempotency_enabled=True,
            enforce_required_keys=enforce_required_keys,
            service_name="test-service",
            lock_ttl=3,
            wait_timeout=0.01,
            inflight_timeout_status_code=425,
            max_cache_body_size=max_cache_body_size,
            policy=policy
            or IdempotencyPolicyConfig(
                default_mode=IdempotencyMode.OPTIONAL_REPLAY,
                route_policies=[
                    IdempotencyPolicy(
                        method="POST",
                        path="/required",
                        mode=IdempotencyMode.REQUIRED_REPLAY,
                    ),
                ],
            ),
        ),
    )

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, Any]:
        body = await request.json()
        return {"body": body, "marker": object_counter()}

    @app.post("/other")
    async def other(request: Request) -> dict[str, Any]:
        body = await request.json()
        return {"other": body, "marker": object_counter()}

    @app.post("/required")
    async def required(request: Request) -> dict[str, Any]:
        body = await request.json()
        return {"body": body}

    @app.post("/domain-ready")
    async def domain_ready(request: Request) -> dict[str, Any]:
        body = await request.json()
        return {"body": body}

    @app.post("/status")
    async def status_route() -> Response:
        return Response(
            '{"error":"temporary"}',
            status_code=cache_status,
            media_type="application/json",
        )

    @app.post("/stream")
    async def stream_route() -> Response:
        media_type = "text/event-stream" if stream else "application/json"
        return Response(f"data: {object_counter()}\n\n", media_type=media_type)

    @app.post("/streaming-response")
    async def streaming_response_route(request: Request) -> StreamingResponse:
        await request.json()

        async def events() -> AsyncIterator[str]:
            yield "data: hello\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/binary")
    async def binary_route() -> Response:
        return Response(
            b"\x00\xff\xfe\x01",
            media_type="application/octet-stream",
            headers={"x-custom": "yes"},
        )

    @app.post("/cookie")
    async def cookie_route() -> Response:
        return Response(
            '{"ok":true}',
            media_type="application/json",
            headers={
                "set-cookie": "session=abc; Path=/; HttpOnly",
                "www-authenticate": 'Bearer realm="test"',
            },
        )

    return TestClient(app)


_counter = 0


def object_counter() -> int:
    global _counter
    _counter += 1
    return _counter


@pytest.fixture(autouse=True)
def reset_counter() -> AsyncIterator[None]:
    global _counter
    _counter = 0
    yield


def test_replays_same_request_with_same_idempotency_key(fake_redis: FakeRedis) -> None:
    client = make_client()

    first = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-1", "X-User-Id": "user-1"},
    )
    second = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-1", "X-User-Id": "user-1"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert second.headers["Idempotency-Replayed"] == "true"
    lock_set = next(call for call in fake_redis.set_calls if call[0].endswith(":lock"))
    assert lock_set[2] is True
    assert lock_set[3] == 3
    assert fake_redis.expire_calls == []


def test_reusing_key_with_different_body_returns_conflict(fake_redis: FakeRedis) -> None:
    client = make_client()

    client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-2", "X-User-Id": "user-1"},
    )
    response = client.post(
        "/echo",
        json={"value": 2},
        headers={"Idempotency-Key": "key-2", "X-User-Id": "user-1"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_key_reused"


def test_reusing_key_with_different_path_returns_conflict(fake_redis: FakeRedis) -> None:
    client = make_client()

    client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-3", "X-User-Id": "user-1"},
    )
    response = client.post(
        "/other",
        json={"value": 1},
        headers={"Idempotency-Key": "key-3", "X-User-Id": "user-1"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_key_reused"


def test_reusing_key_with_different_principal_returns_conflict(fake_redis: FakeRedis) -> None:
    client = make_client()

    client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-4", "X-User-Id": "user-1"},
    )
    response = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-4", "X-User-Id": "user-2"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_key_reused"
    response_keys = [key for key in fake_redis.values if key.endswith(":response")]
    assert len(response_keys) == 1
    assert "user-1" not in response_keys[0]


def test_reusing_key_with_different_principal_after_non_cacheable_response_conflicts(
    fake_redis: FakeRedis,
) -> None:
    client = make_client(cache_status=500)

    first = client.post(
        "/status",
        headers={"Idempotency-Key": "key-4b", "X-User-Id": "user-1"},
    )
    second = client.post(
        "/status",
        headers={"Idempotency-Key": "key-4b", "X-User-Id": "user-2"},
    )

    assert first.status_code == 500
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "idempotency_key_reused"


def test_optional_route_allows_missing_key(fake_redis: FakeRedis) -> None:
    client = make_client()

    response = client.post("/echo", json={"value": 1})

    assert response.status_code == 200


def test_route_policy_matches_path_parameters(fake_redis: FakeRedis) -> None:
    policy = IdempotencyPolicyConfig(
        default_mode=IdempotencyMode.OPTIONAL_REPLAY,
        route_policies=[
            IdempotencyPolicy(
                method="POST",
                path="/items/{item_id}/publish",
                mode=IdempotencyMode.REQUIRED_REPLAY,
            ),
        ],
    )
    app = FastAPI()
    app.add_middleware(
        IdempotencyMiddleware,
        config=IdempotencyConfig(
            redis_host="localhost",
            redis_port=6379,
            redis_db=0,
            redis_password="",
            service_name="test-service",
            policy=policy,
        ),
    )

    @app.post("/items/{item_id}/publish")
    async def publish(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    response = TestClient(app).post("/items/abc/publish")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "idempotency_key_required"


def test_route_policy_matches_optional_trailing_slash(fake_redis: FakeRedis) -> None:
    policy = IdempotencyPolicyConfig(
        route_policies=[
            IdempotencyPolicy(
                method="POST",
                path="/users/",
                mode=IdempotencyMode.REQUIRED_REPLAY,
            ),
        ],
    )

    assert policy.resolve("POST", "/users").mode == IdempotencyMode.REQUIRED_REPLAY
    assert policy.resolve("POST", "/users/").mode == IdempotencyMode.REQUIRED_REPLAY


def test_required_route_rejects_missing_key(fake_redis: FakeRedis) -> None:
    client = make_client()

    response = client.post("/required", json={"value": 1})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "idempotency_key_required"


def test_policy_can_enforce_missing_key_without_global_required_enforcement(
    fake_redis: FakeRedis,
) -> None:
    client = make_client(
        enforce_required_keys=False,
        policy=IdempotencyPolicyConfig(
            default_mode=IdempotencyMode.OPTIONAL_REPLAY,
            route_policies=[
                IdempotencyPolicy(
                    method="POST",
                    path="/domain-ready",
                    mode=IdempotencyMode.DOMAIN_REQUIRED,
                    enforce_missing_key=True,
                ),
            ],
        ),
    )

    response = client.post("/domain-ready", json={"value": 1})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "idempotency_key_required"


@pytest.mark.parametrize("status_code", [429, 500])
def test_does_not_cache_transient_statuses(
    fake_redis: FakeRedis,
    status_code: int,
) -> None:
    client = make_client(cache_status=status_code)

    first = client.post("/status", headers={"Idempotency-Key": "key-status"})
    second = client.post("/status", headers={"Idempotency-Key": "key-status"})

    assert first.status_code == status_code
    assert second.status_code == status_code
    assert "Idempotency-Replayed" not in second.headers
    assert not any(key.endswith(":response") for key in fake_redis.values)


def test_does_not_cache_event_stream_responses(fake_redis: FakeRedis) -> None:
    client = make_client(stream=True)

    first = client.post("/stream", headers={"Idempotency-Key": "key-stream"})
    second = client.post("/stream", headers={"Idempotency-Key": "key-stream"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert "Idempotency-Replayed" not in second.headers


def test_domain_required_event_stream_key_reuse_does_not_execute_again(
    fake_redis: FakeRedis,
) -> None:
    client = make_client(
        stream=True,
        policy=IdempotencyPolicyConfig(
            default_mode=IdempotencyMode.OPTIONAL_REPLAY,
            route_policies=[
                IdempotencyPolicy(
                    method="POST",
                    path="/stream",
                    mode=IdempotencyMode.DOMAIN_REQUIRED,
                    enforce_missing_key=True,
                ),
            ],
        ),
    )

    first = client.post("/stream", headers={"Idempotency-Key": "key-domain-stream"})
    second = client.post("/stream", headers={"Idempotency-Key": "key-domain-stream"})

    assert first.status_code == 200
    assert first.text == "data: 1\n\n"
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "idempotency_key_reused"
    assert _counter == 1


def test_domain_required_retry_after_lock_wait_rechecks_terminal_owner(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client(
        policy=IdempotencyPolicyConfig(
            default_mode=IdempotencyMode.OPTIONAL_REPLAY,
            route_policies=[
                IdempotencyPolicy(
                    method="POST",
                    path="/status",
                    mode=IdempotencyMode.DOMAIN_REQUIRED,
                    enforce_missing_key=True,
                ),
            ],
        ),
        cache_status=503,
    )
    lock_key = "idem:test-service:anonymous:key-domain-inflight:lock"
    fake_redis.values[lock_key] = "first-request"

    async def wait_for_terminal_owner(*args, **kwargs) -> None:
        owner_key = "idem:test-service:key-domain-inflight:owner"
        fake_redis.values[owner_key] = (
            '{"principal_scope":"anonymous",'
            '"request_fingerprint":"stable-fingerprint",'
            '"completed_without_replay":true}'
        )
        fake_redis.values.pop(lock_key, None)
        return None

    monkeypatch.setattr(
        "idempotency.middleware.wait_for_lock_and_get",
        wait_for_terminal_owner,
    )
    monkeypatch.setattr(
        "idempotency.middleware.IdempotencyMiddleware._fingerprint",
        staticmethod(lambda request, body: "stable-fingerprint"),
    )

    response = client.post(
        "/status",
        headers={"Idempotency-Key": "key-domain-inflight"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_key_reused"


def test_domain_required_retry_after_reacquire_rechecks_terminal_owner(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client(
        policy=IdempotencyPolicyConfig(
            default_mode=IdempotencyMode.OPTIONAL_REPLAY,
            route_policies=[
                IdempotencyPolicy(
                    method="POST",
                    path="/status",
                    mode=IdempotencyMode.DOMAIN_REQUIRED,
                    enforce_missing_key=True,
                ),
            ],
        ),
        cache_status=503,
    )
    lock_key = "idem:test-service:anonymous:key-domain-reacquire:lock"
    owner_key = "idem:test-service:key-domain-reacquire:owner"
    fake_redis.values[lock_key] = "first-request"

    async def wait_without_terminal_owner(*args, **kwargs) -> None:
        fake_redis.values.pop(lock_key, None)
        return None

    real_set = fake_redis.set

    async def set_and_complete_owner(
        key: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool:
        result = await real_set(key, value, nx=nx, ex=ex)
        if key == lock_key and result:
            fake_redis.values[owner_key] = (
                '{"principal_scope":"anonymous",'
                '"request_fingerprint":"stable-fingerprint",'
                '"completed_without_replay":true}'
            )
        return result

    monkeypatch.setattr(fake_redis, "set", set_and_complete_owner)
    monkeypatch.setattr(
        "idempotency.middleware.wait_for_lock_and_get",
        wait_without_terminal_owner,
    )
    monkeypatch.setattr(
        "idempotency.middleware.IdempotencyMiddleware._fingerprint",
        staticmethod(lambda request, body: "stable-fingerprint"),
    )

    response = client.post(
        "/status",
        headers={"Idempotency-Key": "key-domain-reacquire"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_key_reused"


def test_domain_required_retry_with_expired_lock_does_not_execute_again(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client(
        policy=IdempotencyPolicyConfig(
            default_mode=IdempotencyMode.OPTIONAL_REPLAY,
            route_policies=[
                IdempotencyPolicy(
                    method="POST",
                    path="/echo",
                    mode=IdempotencyMode.DOMAIN_REQUIRED,
                    enforce_missing_key=True,
                ),
            ],
        ),
    )
    fake_redis.values["idem:test-service:key-expired-lock:owner"] = (
        '{"principal_scope":"anonymous",'
        '"request_fingerprint":"stable-fingerprint",'
        '"completed_without_replay":false}'
    )
    monkeypatch.setattr(
        "idempotency.middleware.IdempotencyMiddleware._fingerprint",
        staticmethod(lambda request, body: "stable-fingerprint"),
    )

    response = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-expired-lock"},
    )

    assert response.status_code == 425
    assert response.json()["error"]["code"] == "idempotency_request_in_progress"
    assert _counter == 0


def test_domain_required_compatible_owner_claim_race_does_not_execute_again(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client(
        policy=IdempotencyPolicyConfig(
            default_mode=IdempotencyMode.OPTIONAL_REPLAY,
            route_policies=[
                IdempotencyPolicy(
                    method="POST",
                    path="/echo",
                    mode=IdempotencyMode.DOMAIN_REQUIRED,
                    enforce_missing_key=True,
                ),
            ],
        ),
    )
    owner_key = "idem:test-service:key-owner-race:owner"
    real_set = fake_redis.set

    async def lose_owner_claim(
        key: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool:
        if key == owner_key and nx:
            fake_redis.values[owner_key] = value
            return False
        return await real_set(key, value, nx=nx, ex=ex)

    monkeypatch.setattr(fake_redis, "set", lose_owner_claim)

    response = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-owner-race"},
    )

    assert response.status_code == 425
    assert response.json()["error"]["code"] == "idempotency_request_in_progress"
    assert _counter == 0


def test_streaming_response_with_body_can_complete(fake_redis: FakeRedis) -> None:
    client = make_client()

    response = client.post(
        "/streaming-response",
        json={"value": 1},
        headers={"Idempotency-Key": "key-streaming-response"},
    )

    assert response.status_code == 200
    assert response.text == "data: hello\n\n"


def test_inflight_duplicate_uses_configured_wait_timeout_and_replays(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client()
    observed: dict[str, float] = {}
    cached = CachedResponse(
        status_code=200,
        headers={"content-type": "application/json"},
        body='{"ok":true}',
        created_at=datetime.utcnow(),
        fingerprint="stable-fingerprint",
        principal_scope="anonymous",
    )

    async def wait_for_lock_and_get(*args, max_wait: float, **kwargs) -> CachedResponse:
        observed["max_wait"] = max_wait
        return cached

    monkeypatch.setattr(
        "idempotency.middleware.wait_for_lock_and_get",
        wait_for_lock_and_get,
    )
    monkeypatch.setattr(
        "idempotency.middleware.IdempotencyMiddleware._fingerprint",
        staticmethod(lambda request, body: "stable-fingerprint"),
    )
    fake_redis.values["idem:test-service:anonymous:key-wait:lock"] = "existing"

    response = client.post("/echo", json={"value": 1}, headers={"Idempotency-Key": "key-wait"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert response.headers["Idempotency-Replayed"] == "true"
    assert observed["max_wait"] == 0.01


def test_inflight_duplicate_timeout_uses_configured_status(fake_redis: FakeRedis) -> None:
    client = make_client()
    fake_redis.values["idem:test-service:anonymous:key-timeout:lock"] = "existing"

    response = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-timeout"},
    )

    assert response.status_code == 425
    assert response.json()["error"]["code"] == "idempotency_request_in_progress"


@pytest.mark.asyncio
async def test_release_lock_uses_atomic_compare_delete(fake_redis: FakeRedis) -> None:
    key = "idem:test-service:anonymous:key-release:lock"
    fake_redis.values[key] = "new-token"

    await release_lock(
        fake_redis,
        "test-service",
        "anonymous",
        "key-release",
        lock_token="old-token",
    )

    assert fake_redis.values[key] == "new-token"
    assert fake_redis.eval_calls


@pytest.mark.asyncio
async def test_release_lock_requires_token(fake_redis: FakeRedis) -> None:
    with pytest.raises(ValueError):
        await release_lock(
            fake_redis,
            "test-service",
            "anonymous",
            "key-release-no-token",
            lock_token=None,
        )


@pytest.mark.asyncio
async def test_renew_lock_only_extends_owned_lock(fake_redis: FakeRedis) -> None:
    key = "idem:test-service:anonymous:key-renew:lock"
    fake_redis.values[key] = "my-token"

    owned = await renew_lock(
        fake_redis,
        "test-service",
        "anonymous",
        "key-renew",
        "my-token",
        ttl_ms=30000,
    )
    assert owned is True
    assert fake_redis.eval_calls

    fake_redis.values[key] = "other-token"
    not_owned = await renew_lock(
        fake_redis,
        "test-service",
        "anonymous",
        "key-renew",
        "stale-token",
        ttl_ms=30000,
    )
    assert not_owned is False


def test_rejects_malformed_idempotency_key(fake_redis: FakeRedis) -> None:
    client = make_client()

    response = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "bad key with spaces!"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "idempotency_key_invalid"


def test_rejects_overlong_idempotency_key(fake_redis: FakeRedis) -> None:
    client = make_client()

    response = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "k" * 256},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "idempotency_key_invalid"


def test_redis_unavailable_fails_open_for_optional_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def connect(config: IdempotencyConfig) -> None:
        raise redis.exceptions.ConnectionError("redis down")

    monkeypatch.setattr(AsyncRedisPool, "connect", connect)
    client = make_client()

    response = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-fail-open"},
    )

    assert response.status_code == 200


def test_redis_unavailable_returns_503_for_required_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def connect(config: IdempotencyConfig) -> None:
        raise redis.exceptions.ConnectionError("redis down")

    monkeypatch.setattr(AsyncRedisPool, "connect", connect)
    client = make_client()

    response = client.post(
        "/required",
        json={"value": 1},
        headers={"Idempotency-Key": "key-fail-required"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "idempotency_store_unavailable"


def test_caches_binary_response_and_replays_byte_for_byte(
    fake_redis: FakeRedis,
) -> None:
    client = make_client()

    first = client.post("/binary", headers={"Idempotency-Key": "key-binary"})
    second = client.post("/binary", headers={"Idempotency-Key": "key-binary"})

    assert first.status_code == 200
    assert first.content == b"\x00\xff\xfe\x01"
    assert first.headers["x-custom"] == "yes"
    assert second.status_code == 200
    assert second.content == first.content
    assert second.headers["Idempotency-Replayed"] == "true"
    assert second.headers["x-custom"] == "yes"


def test_does_not_cache_oversized_body(fake_redis: FakeRedis) -> None:
    client = make_client(max_cache_body_size=16)

    first = client.post(
        "/echo",
        json={"value": "x" * 64},
        headers={"Idempotency-Key": "key-oversized"},
    )
    second = client.post(
        "/echo",
        json={"value": "x" * 64},
        headers={"Idempotency-Key": "key-oversized"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert _counter == 2
    assert not any(key.endswith(":response") for key in fake_redis.values)


def test_replay_strips_set_cookie_and_challenge_headers(
    fake_redis: FakeRedis,
) -> None:
    client = make_client()

    first = client.post("/cookie", headers={"Idempotency-Key": "key-cookie"})
    second = client.post("/cookie", headers={"Idempotency-Key": "key-cookie"})

    assert first.status_code == 200
    assert first.headers.get("set-cookie") is not None
    assert second.status_code == 200
    assert "set-cookie" not in second.headers
    assert "www-authenticate" not in second.headers
    assert second.headers["Idempotency-Replayed"] == "true"
