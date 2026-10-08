import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx
import pytest
import redis.exceptions
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse

from idempotency import (
    AsyncRedisPool,
    CachedResponse,
    IdempotencyConfig,
    IdempotencyDecision,
    IdempotencyMiddleware,
)
from idempotency.models import IdempotencyMode, IdempotencyPolicy, IdempotencyPolicyConfig
from idempotency.storage import (
    _RELEASE_LOCK_LUA,
    _RENEW_LOCK_LUA,
    acquire_lock,
    release_lock,
    renew_lock,
)


class FakeRedis:
    """In-memory Redis stand-in.

    Models only what the middleware depends on: SET NX EX atomicity, TTL
    expiry, and the two lock scripts. `eval` dispatches on script identity and
    raises on anything unmodelled, so a new script cannot be silently executed
    with release semantics.

    Reads that care about expiry must go through `await get()`. Touching
    `.values` directly is a raw storage view and bypasses TTL handling.
    """

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}
        self.set_calls: list[tuple[str, str, bool, int | None]] = []
        self.expire_calls: list[tuple[str, int]] = []
        self.eval_calls: list[tuple[str, tuple[Any, ...]]] = []
        self._deadlines: dict[str, float] = {}
        self._clock = 0.0

    def advance(self, seconds: float) -> None:
        """Move the fake clock forward so TTL expiry becomes observable."""
        self._clock += seconds

    def _set_ttl(self, key: str, seconds: float) -> None:
        self.expirations[key] = int(seconds)
        self._deadlines[key] = self._clock + seconds

    def _evict_if_expired(self, key: str) -> None:
        deadline = self._deadlines.get(key)
        if deadline is not None and self._clock >= deadline:
            self.delete_sync(key)

    def delete_sync(self, key: str) -> None:
        self.values.pop(key, None)
        self.expirations.pop(key, None)
        self._deadlines.pop(key, None)

    async def get(self, key: str) -> str | None:
        self._evict_if_expired(key)
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self._set_ttl(key, ttl)

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
        self.set_calls.append((key, value, nx, ex))
        self._evict_if_expired(key)
        if nx and key in self.values:
            return False
        self.values[key] = value
        if ex is not None:
            self._set_ttl(key, ex)
        else:
            # A plain SET clears any TTL, as Redis does.
            self.expirations.pop(key, None)
            self._deadlines.pop(key, None)
        return True

    async def expire(self, key: str, ttl: int) -> None:
        self.expire_calls.append((key, ttl))
        self._set_ttl(key, ttl)

    async def delete(self, key: str) -> None:
        self.delete_sync(key)

    async def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> int:
        self.eval_calls.append((script, keys_and_args))
        key, token = keys_and_args[0], keys_and_args[1]
        if self.values.get(key) != token:
            return 0
        if script == _RELEASE_LOCK_LUA:
            self.delete_sync(key)
            return 1
        if script == _RENEW_LOCK_LUA:
            # Redis pexpire counts milliseconds.
            self._set_ttl(key, int(keys_and_args[2]) / 1000)
            return 1
        raise AssertionError(f"unmodelled Lua script: {script.strip()[:40]!r}")


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
    principal_extractor=None,
    flaky_outcomes: list[int | Exception] | None = None,
    raise_server_exceptions: bool = True,
    decision_recorder=None,
) -> TestClient:
    app = FastAPI()
    remaining_outcomes = list(flaky_outcomes or [])
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
            principal_extractor=principal_extractor,
            decision_recorder=decision_recorder,
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

    @app.put("/echo")
    async def put_echo(request: Request) -> dict[str, Any]:
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

    @app.post("/flaky")
    async def flaky_route() -> Response:
        # Each run ends the way the next entry of flaky_outcomes says: with
        # that status code, or by raising that exception.
        run = object_counter()
        outcome = remaining_outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return Response(
            f'{{"run":{run}}}',
            status_code=outcome,
            media_type="application/json",
        )

    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


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


def test_put_replays_same_request_with_same_idempotency_key(
    fake_redis: FakeRedis,
) -> None:
    client = make_client()

    first = client.put(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "put-key-1", "X-User-Id": "user-1"},
    )
    second = client.put(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "put-key-1", "X-User-Id": "user-1"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert first.json()["marker"] == 1
    assert second.headers["Idempotency-Replayed"] == "true"
    assert _counter == 1


def test_put_with_new_key_is_a_new_operation(fake_redis: FakeRedis) -> None:
    client = make_client()

    first = client.put(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "put-key-1", "X-User-Id": "user-1"},
    )
    second = client.put(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "put-key-2", "X-User-Id": "user-1"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["marker"] == 1
    assert second.json()["marker"] == 2
    assert "Idempotency-Replayed" not in second.headers
    assert _counter == 2


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


def test_route_policy_matches_path_converter_parameters(fake_redis: FakeRedis) -> None:
    policy = IdempotencyPolicyConfig(
        route_policies=[
            IdempotencyPolicy(
                method="DELETE",
                path="/models/{model_name:path}",
                mode=IdempotencyMode.DOMAIN_REQUIRED,
            ),
        ],
    )

    assert policy.resolve("DELETE", "/models/llama3.2").mode == (IdempotencyMode.DOMAIN_REQUIRED)
    assert policy.resolve("DELETE", "/models/hf.co/bartowski/model").mode == (
        IdempotencyMode.DOMAIN_REQUIRED
    )


def test_required_route_rejects_missing_key(fake_redis: FakeRedis) -> None:
    client = make_client()

    response = client.post("/required", json={"value": 1})

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "idempotency_key_required",
            "message": "Idempotency-Key header is required for this endpoint.",
            "details": {},
            "field_errors": [],
            "request_id": None,
        }
    }


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


def test_policy_can_opt_out_of_global_required_enforcement(
    fake_redis: FakeRedis,
) -> None:
    """A route with enforce_missing_key=False must not require a key even when
    the global enforce_required_keys flag is on (e.g. tools-service /mcp)."""
    client = make_client(
        enforce_required_keys=True,
        policy=IdempotencyPolicyConfig(
            default_mode=IdempotencyMode.OPTIONAL_REPLAY,
            route_policies=[
                IdempotencyPolicy(
                    method="POST",
                    path="/domain-ready",
                    mode=IdempotencyMode.DOMAIN_REQUIRED,
                    enforce_missing_key=False,
                ),
            ],
        ),
    )

    response = client.post("/domain-ready", json={"value": 1})

    assert response.status_code == 200
    assert response.json() == {"body": {"value": 1}}


def test_policy_without_override_falls_back_to_global_enforcement(
    fake_redis: FakeRedis,
) -> None:
    """A route with enforce_missing_key=None (default) enforces when the global
    flag is on and the mode is required_replay or domain_required."""
    client = make_client(
        enforce_required_keys=True,
        policy=IdempotencyPolicyConfig(
            default_mode=IdempotencyMode.OPTIONAL_REPLAY,
            route_policies=[
                IdempotencyPolicy(
                    method="POST",
                    path="/required",
                    mode=IdempotencyMode.REQUIRED_REPLAY,
                ),
            ],
        ),
    )

    response = client.post("/required", json={"value": 1})

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
    fake_redis.expirations[key] = 3

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
    # The renew script pexpires the lock, it must never remove it. Redis counts
    # milliseconds, so 30000ms lands as a 30 second TTL, not the original 3.
    assert fake_redis.values.get(key) == "my-token"
    assert fake_redis.expirations[key] == 30

    fake_redis.values[key] = "other-token"
    not_owned = await renew_lock(
        fake_redis,
        "test-service",
        "anonymous",
        "key-renew",
        "stale-token",
        ttl_ms=999_000,
    )
    assert not_owned is False
    # A stale token leaves the live holder's lock alone and extends nothing,
    # so the TTL stays at 30 rather than moving to the 999000 that was offered.
    assert fake_redis.values.get(key) == "other-token"
    assert fake_redis.expirations[key] == 30


@pytest.mark.asyncio
async def test_lock_expires_and_can_be_reacquired_after_ttl(fake_redis: FakeRedis) -> None:
    token = await acquire_lock(fake_redis, "test-service", "anonymous", "key-ttl", lock_ttl=3)
    assert token is not None
    lock_key = "idem:test-service:anonymous:key-ttl:lock"

    fake_redis.advance(2.9)
    assert await fake_redis.get(lock_key) == token, "must survive until the TTL actually lapses"

    fake_redis.advance(0.2)
    assert await fake_redis.get(lock_key) is None, "an elapsed TTL must evict the key"

    retaken = await acquire_lock(fake_redis, "test-service", "anonymous", "key-ttl", lock_ttl=3)
    assert retaken is not None
    assert retaken != token


@pytest.mark.asyncio
async def test_stale_release_cannot_delete_a_reacquired_lock(fake_redis: FakeRedis) -> None:
    """The compare-and-delete contract. After a TTL lapse another caller may
    take the lock; the previous holder's late release must not remove it,
    because that would let a third request execute a duplicate side effect."""
    first = await acquire_lock(fake_redis, "test-service", "anonymous", "key-stale", lock_ttl=1)
    assert first is not None

    fake_redis.advance(1.1)
    second = await acquire_lock(fake_redis, "test-service", "anonymous", "key-stale", lock_ttl=5)
    assert second is not None and second != first

    await release_lock(fake_redis, "test-service", "anonymous", "key-stale", lock_token=first)

    lock_key = "idem:test-service:anonymous:key-stale:lock"
    assert await fake_redis.get(lock_key) == second, "the new holder keeps its lock"
    assert fake_redis.expirations[lock_key] == 5, "and keeps its TTL"

    await release_lock(fake_redis, "test-service", "anonymous", "key-stale", lock_token=second)
    assert await fake_redis.get(lock_key) is None, "the owner still releases its own lock"


@pytest.mark.asyncio
async def test_renew_extends_beyond_the_original_expiry(fake_redis: FakeRedis) -> None:
    token = await acquire_lock(fake_redis, "test-service", "anonymous", "key-keep", lock_ttl=3)
    assert token is not None
    lock_key = "idem:test-service:anonymous:key-keep:lock"

    assert await renew_lock(
        fake_redis, "test-service", "anonymous", "key-keep", token, ttl_ms=30_000
    )

    fake_redis.advance(4.0)
    assert await fake_redis.get(lock_key) == token, "renewal outlasted the original 3s TTL"


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
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def connect(config: IdempotencyConfig) -> None:
        raise redis.exceptions.ConnectionError("redis.exceptions.ConnectionError: redis down")

    monkeypatch.setattr(AsyncRedisPool, "connect", connect)
    client = make_client()

    with caplog.at_level("WARNING"):
        response = client.post(
            "/required",
            json={"value": 1},
            headers={"Idempotency-Key": "key-fail-required"},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "idempotency_store_unavailable"
    assert "Idempotency store unavailable for POST /required" in caplog.text
    assert "redis.exceptions" not in caplog.text
    assert "redis down" not in caplog.text


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


async def _extractor_from_header(request: Request) -> str | None:
    return request.headers.get("X-Authenticated-User-Id")


async def _extractor_returns_none(request: Request) -> str | None:
    return None


def test_principal_extractor_used_for_scope(fake_redis: FakeRedis) -> None:
    client = make_client(principal_extractor=_extractor_from_header)

    first = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-ext-1", "X-Authenticated-User-Id": "user-1"},
    )
    second = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-ext-1", "X-Authenticated-User-Id": "user-1"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.headers["Idempotency-Replayed"] == "true"
    response_keys = [key for key in fake_redis.values if key.endswith(":response")]
    assert len(response_keys) == 1
    assert "user:" in response_keys[0]
    assert "x-authenticated-user-id" not in response_keys[0]


def test_principal_extractor_ignores_client_supplied_x_user_id(
    fake_redis: FakeRedis,
) -> None:
    client = make_client(principal_extractor=_extractor_from_header)

    first = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-ext-2", "X-User-Id": "spoofed-user"},
    )
    second = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-ext-2", "X-User-Id": "spoofed-user"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.headers["Idempotency-Replayed"] == "true"
    response_keys = [key for key in fake_redis.values if key.endswith(":response")]
    assert len(response_keys) == 1
    assert "spoofed-user" not in response_keys[0]


def test_principal_extractor_returns_none_falls_back_to_anonymous(
    fake_redis: FakeRedis,
) -> None:
    client = make_client(principal_extractor=_extractor_returns_none)

    first = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-ext-3", "X-User-Id": "user-1"},
    )
    second = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-ext-3", "X-User-Id": "user-1"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.headers["Idempotency-Replayed"] == "true"
    response_keys = [key for key in fake_redis.values if key.endswith(":response")]
    assert len(response_keys) == 1
    assert "anonymous" in response_keys[0]


def test_principal_extractor_separates_users(fake_redis: FakeRedis) -> None:
    client = make_client(principal_extractor=_extractor_from_header)

    first = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-ext-4", "X-Authenticated-User-Id": "user-1"},
    )
    second = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-ext-4", "X-Authenticated-User-Id": "user-2"},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "idempotency_key_reused"


def test_no_extractor_uses_header_candidates_backward_compatible(
    fake_redis: FakeRedis,
) -> None:
    client = make_client()

    first = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-ext-5", "X-User-Id": "user-1"},
    )
    second = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-ext-5", "X-User-Id": "user-1"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.headers["Idempotency-Replayed"] == "true"
    response_keys = [key for key in fake_redis.values if key.endswith(":response")]
    assert len(response_keys) == 1
    assert "x-user-id" in response_keys[0]


# ---------------------------------------------------------------------------
# Spec TS-13: a Redis failure while releasing the lock must not turn an
# already-successful response into a 500, and a 401/403 response must not
# leave the key's owner record claimed for the full 24h TTL.
# ---------------------------------------------------------------------------


def test_release_lock_failure_does_not_replace_a_successful_response(
    fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    from idempotency import middleware

    async def failing_release_lock(*args, **kwargs):
        raise redis.exceptions.RedisError("connection reset")

    monkeypatch.setattr(middleware, "release_lock", failing_release_lock)
    client = make_client()

    response = client.post(
        "/echo",
        json={"value": 1},
        headers={"Idempotency-Key": "key-release-fail", "X-User-Id": "user-1"},
    )

    assert response.status_code == 200
    assert response.json()["body"] == {"value": 1}


def test_owner_record_is_cleared_on_an_unauthorised_response(
    fake_redis: FakeRedis,
) -> None:
    client = make_client(cache_status=401)

    first = client.post(
        "/status",
        json={},
        headers={"Idempotency-Key": "key-401", "X-User-Id": "user-1"},
    )
    assert first.status_code == 401

    owner_keys = [key for key in fake_redis.values if key.endswith(":owner")]
    assert owner_keys == []

    # A retry with a *different* principal must not be rejected as a key
    # reuse conflict: the failed attempt released its claim on the key.
    second = client.post(
        "/status",
        json={},
        headers={"Idempotency-Key": "key-401", "X-User-Id": "user-2"},
    )
    assert second.status_code == 401


# ---------------------------------------------------------------------------
# rerun_after_failure: a domain-required route whose handler may run again
# after a run that failed frees its key then, instead of closing it. A run
# that succeeded is still replayed and a run in flight still refuses the key.
# ---------------------------------------------------------------------------


def _flaky_policy(*, rerun_after_failure: bool) -> IdempotencyPolicyConfig:
    return IdempotencyPolicyConfig(
        default_mode=IdempotencyMode.OPTIONAL_REPLAY,
        route_policies=[
            IdempotencyPolicy(
                method="POST",
                path="/flaky",
                mode=IdempotencyMode.DOMAIN_REQUIRED,
                enforce_missing_key=True,
                rerun_after_failure=rerun_after_failure,
            ),
        ],
    )


@pytest.mark.parametrize("status_code", [429, 500, 503])
def test_rerun_after_failure_runs_the_key_again_after_a_transient_status(
    fake_redis: FakeRedis,
    status_code: int,
) -> None:
    client = make_client(
        policy=_flaky_policy(rerun_after_failure=True),
        flaky_outcomes=[status_code, 200],
    )
    headers = {"Idempotency-Key": "key-rerun-status"}

    first = client.post("/flaky", json={"value": 1}, headers=headers)
    second = client.post("/flaky", json={"value": 1}, headers=headers)
    third = client.post("/flaky", json={"value": 1}, headers=headers)

    assert first.status_code == status_code
    assert second.status_code == 200
    assert second.json() == {"run": 2}
    assert "Idempotency-Replayed" not in second.headers
    # The run that succeeded closes the key: its answer is replayed.
    assert third.status_code == 200
    assert third.json() == {"run": 2}
    assert third.headers["Idempotency-Replayed"] == "true"
    assert _counter == 2


def test_rerun_after_failure_runs_the_key_again_after_the_handler_raised(
    fake_redis: FakeRedis,
) -> None:
    client = make_client(
        policy=_flaky_policy(rerun_after_failure=True),
        flaky_outcomes=[RuntimeError("embedding model down"), 200],
        raise_server_exceptions=False,
    )
    headers = {"Idempotency-Key": "key-rerun-raise"}

    first = client.post("/flaky", json={"value": 1}, headers=headers)
    second = client.post("/flaky", json={"value": 1}, headers=headers)

    assert first.status_code == 500
    assert second.status_code == 200
    assert second.json() == {"run": 2}
    assert "Idempotency-Replayed" not in second.headers


def test_rerun_after_failure_keeps_the_key_closed_after_a_client_error(
    fake_redis: FakeRedis,
) -> None:
    client = make_client(
        policy=_flaky_policy(rerun_after_failure=True),
        flaky_outcomes=[422, 200],
    )
    headers = {"Idempotency-Key": "key-rerun-422"}

    first = client.post("/flaky", json={"value": 1}, headers=headers)
    second = client.post("/flaky", json={"value": 1}, headers=headers)

    assert first.status_code == 422
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "idempotency_key_reused"
    assert _counter == 1


def test_rerun_after_failure_still_refuses_a_key_whose_request_is_in_flight(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client(
        policy=_flaky_policy(rerun_after_failure=True),
        flaky_outcomes=[200],
    )
    fake_redis.values["idem:test-service:key-rerun-in-flight:owner"] = (
        '{"principal_scope":"anonymous",'
        '"request_fingerprint":"stable-fingerprint",'
        '"completed_without_replay":false}'
    )
    monkeypatch.setattr(
        "idempotency.middleware.IdempotencyMiddleware._fingerprint",
        staticmethod(lambda request, body: "stable-fingerprint"),
    )

    response = client.post(
        "/flaky",
        json={"value": 1},
        headers={"Idempotency-Key": "key-rerun-in-flight"},
    )

    assert response.status_code == 425
    assert response.json()["error"]["code"] == "idempotency_request_in_progress"
    assert _counter == 0


def test_rerun_after_failure_survives_a_store_that_cannot_free_the_key(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from idempotency import middleware

    async def failing_delete_key_owner(*args, **kwargs):
        raise redis.exceptions.RedisError("connection reset")

    monkeypatch.setattr(middleware, "delete_key_owner", failing_delete_key_owner)
    client = make_client(
        policy=_flaky_policy(rerun_after_failure=True),
        flaky_outcomes=[503, RuntimeError("embedding model down")],
        raise_server_exceptions=False,
    )

    # The handler's own outcome reaches the caller; the key stays as the
    # failed run left it and expires with its TTL.
    answered = client.post(
        "/flaky", json={"value": 1}, headers={"Idempotency-Key": "key-rerun-a"}
    )
    raised = client.post(
        "/flaky", json={"value": 1}, headers={"Idempotency-Key": "key-rerun-b"}
    )

    assert answered.status_code == 503
    assert answered.json() == {"run": 1}
    assert raised.status_code == 500


@pytest.mark.parametrize(
    ("first_outcome", "first_status", "second_status", "second_code"),
    [
        (503, 503, 409, "idempotency_key_reused"),
        (RuntimeError("embedding model down"), 500, 425, "idempotency_request_in_progress"),
    ],
)
def test_without_rerun_after_failure_a_failed_run_keeps_its_key(
    fake_redis: FakeRedis,
    first_outcome: int | Exception,
    first_status: int,
    second_status: int,
    second_code: str,
) -> None:
    client = make_client(
        policy=_flaky_policy(rerun_after_failure=False),
        flaky_outcomes=[first_outcome, 200],
        raise_server_exceptions=False,
    )
    headers = {"Idempotency-Key": "key-no-rerun"}

    first = client.post("/flaky", json={"value": 1}, headers=headers)
    second = client.post("/flaky", json={"value": 1}, headers=headers)

    assert first.status_code == first_status
    assert second.status_code == second_status
    assert second.json()["error"]["code"] == second_code
    assert _counter == 1


# --- TBD-1: duplicate execution under concurrency ----------------------------
#
# The pre-existing race tests all pre-seeded a lock while using
# DOMAIN_REQUIRED, whose owner_existed guard rejects a duplicate before the
# lock is taken. That is why a real duplicate-execution defect survived in
# REQUIRED_REPLAY. These tests drive two live requests through the app instead.


def _policy_for(mode: IdempotencyMode) -> IdempotencyPolicyConfig:
    return IdempotencyPolicyConfig(
        default_mode=mode,
        route_policies=[
            IdempotencyPolicy(
                method="POST",
                path="/echo",
                mode=mode,
                enforce_missing_key=True,
            ),
        ],
    )


async def _fire_concurrent(mode: IdempotencyMode, key: str) -> list[int]:
    """Two live requests, one key, same event loop."""
    client = make_client(policy=_policy_for(mode))
    transport = httpx.ASGITransport(app=client.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        responses = await asyncio.gather(
            *(
                http.post(
                    "/echo",
                    json={"value": 1},
                    headers={"Idempotency-Key": key},
                )
                for _ in range(2)
            )
        )
    return [r.status_code for r in responses]


@pytest.mark.asyncio
async def test_concurrent_duplicates_execute_once_under_domain_required(
    fake_redis: FakeRedis,
) -> None:
    """`domain_required` promises a single side effect for one key."""
    statuses = await _fire_concurrent(IdempotencyMode.DOMAIN_REQUIRED, "conc-domain")

    assert _counter == 1, f"handler ran {_counter} times; statuses={statuses}"
    assert 200 in statuses, "the original request must succeed"


@pytest.mark.asyncio
async def test_required_replay_does_not_re_execute_after_wait_timeout(
    fake_redis: FakeRedis,
) -> None:
    """`required_replay` promises to replay the cached response.

    Guards the defect fixed as TBD-1: a waiter that timed out used to re-acquire
    the lock and re-run the handler without re-reading the cached response, and
    `wait_for_lock_and_get` used to sleep past its final read. The reproduction
    depends on the wait outliving the first request, which is why the test
    client's `wait_timeout` sits far below the poll interval.
    """
    statuses = await _fire_concurrent(IdempotencyMode.REQUIRED_REPLAY, "conc-required")

    assert _counter == 1, f"handler ran {_counter} times for one key; statuses={statuses}"
    assert set(statuses) <= {200, 425}, f"unexpected statuses {statuses}"


# --- T2: the decision recorder ---------------------------------------------


class _Recorder:
    def __init__(self) -> None:
        self.decisions: list[IdempotencyDecision] = []

    def __call__(self, decision: IdempotencyDecision) -> None:
        self.decisions.append(decision)

    @property
    def outcomes(self) -> list[str]:
        return [d.outcome for d in self.decisions]


def test_records_executed_then_replayed(fake_redis: FakeRedis) -> None:
    recorder = _Recorder()
    client = make_client(decision_recorder=recorder)

    first = client.post("/echo", json={"v": 1}, headers={"Idempotency-Key": "k"})
    second = client.post("/echo", json={"v": 1}, headers={"Idempotency-Key": "k"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert recorder.outcomes == ["executed", "replayed"]
    executed, replayed = recorder.decisions
    assert (executed.replayed, executed.lock_acquired) == (False, True)
    # A replay returns the stored response without ever taking the lock.
    assert (replayed.replayed, replayed.lock_acquired) == (True, False)


def test_records_bypassed_when_key_absent_and_optional(
    fake_redis: FakeRedis,
) -> None:
    recorder = _Recorder()
    client = make_client(decision_recorder=recorder)

    response = client.post("/echo", json={"v": 1})

    assert response.status_code == 200
    assert recorder.outcomes == ["bypassed"]


def test_records_key_required(fake_redis: FakeRedis) -> None:
    recorder = _Recorder()
    client = make_client(decision_recorder=recorder)

    response = client.post("/required")

    assert response.status_code == 400
    assert recorder.outcomes == ["key_required"]
    assert recorder.decisions[0].error_code == "idempotency_key_required"


def test_records_key_invalid(fake_redis: FakeRedis) -> None:
    recorder = _Recorder()
    client = make_client(decision_recorder=recorder)

    response = client.post(
        "/echo",
        json={"v": 1},
        headers={"Idempotency-Key": "bad key!"},
    )

    assert response.status_code == 400
    assert recorder.outcomes == ["key_invalid"]
    assert recorder.decisions[0].error_code == "idempotency_key_invalid"


def test_records_conflict_on_fingerprint_mismatch(
    fake_redis: FakeRedis,
) -> None:
    recorder = _Recorder()
    client = make_client(decision_recorder=recorder)

    client.post("/echo", json={"v": 1}, headers={"Idempotency-Key": "k"})
    second = client.post("/echo", json={"v": 2}, headers={"Idempotency-Key": "k"})

    assert second.status_code == 409
    assert recorder.outcomes == ["executed", "conflict"]
    assert recorder.decisions[1].status_code == 409
    assert recorder.decisions[1].lock_acquired is False
    assert _counter == 1


def test_records_in_flight_for_domain_required_duplicate(
    fake_redis: FakeRedis,
) -> None:
    """A duplicate arriving while the first still holds the lock, with a
    compatible owner already on file, is refused as in-flight rather than
    executed. The owner must be compatible or this would be a 409 instead."""
    recorder = _Recorder()
    # cache_status=503 so the first request publishes nothing: a 5xx is never
    # cacheable, which leaves the owner recorded with no cached response.
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
        decision_recorder=recorder,
    )
    lock_key = "idem:test-service:anonymous:dup:lock"
    owner_key = "idem:test-service:dup:owner"

    # The duplicate's fingerprint must match the owner's. Capture it from the
    # first request by reading the owner the middleware wrote.
    client.post("/status", headers={"Idempotency-Key": "dup"})
    owner_raw = fake_redis.values.get(owner_key)
    assert owner_raw, "the first request must have recorded an owner"
    fingerprint = json.loads(owner_raw)["request_fingerprint"]
    assert fingerprint

    # Now the duplicate: the lock is still held and nothing was cached, so the
    # domain_required in-flight branch must fire before any execution.
    fake_redis.values[lock_key] = "still-held"
    fake_redis.values.pop(owner_key)
    fake_redis.values[owner_key] = json.dumps(
        {
            "principal_scope": "anonymous",
            "request_fingerprint": fingerprint,
            "completed_without_replay": False,
        }
    )

    response = client.post("/status", headers={"Idempotency-Key": "dup"})

    assert response.status_code == 425
    assert recorder.outcomes[-1] == "in_flight"
    assert recorder.decisions[-1].lock_acquired is False


def test_records_completed_no_replay_for_domain_required_stream(
    fake_redis: FakeRedis,
) -> None:
    recorder = _Recorder()
    client = make_client(
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
        stream=True,
        decision_recorder=recorder,
    )

    response = client.post("/stream", headers={"Idempotency-Key": "s"})

    assert response.status_code == 200
    assert recorder.outcomes == ["completed_no_replay"]
    assert recorder.decisions[0].cacheable is False


def test_records_store_unavailable(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _Recorder()
    # /required is REQUIRED_REPLAY under the default factory, so a store
    # outage must fail closed with 503 rather than executing the route. The key
    # is mandatory there, and without it the request is rejected at preflight
    # before any pool is opened.
    client = make_client(decision_recorder=recorder)

    async def fail(config: IdempotencyConfig) -> FakeRedis:
        raise redis.exceptions.RedisError("down")

    monkeypatch.setattr(AsyncRedisPool, "connect", fail)

    response = client.post("/required", json={"v": 1}, headers={"Idempotency-Key": "k"})

    assert response.status_code == 503
    assert recorder.outcomes == ["store_unavailable"]
    assert recorder.decisions[0].error_code == "idempotency_store_unavailable"


def test_route_label_uses_policy_template_not_request_path(
    fake_redis: FakeRedis,
) -> None:
    """Two concrete paths under one template must produce one label, otherwise
    the metric grows a series per key."""
    recorder = _Recorder()
    client = make_client(
        policy=IdempotencyPolicyConfig(
            default_mode=IdempotencyMode.OPTIONAL_REPLAY,
            route_policies=[
                IdempotencyPolicy(
                    method="POST",
                    path="/echo",
                    mode=IdempotencyMode.REQUIRED_REPLAY,
                ),
            ],
        ),
        decision_recorder=recorder,
    )

    for key in ("a-1", "a-2", "a-3"):
        client.post("/echo", json={"v": 1}, headers={"Idempotency-Key": key})

    assert {d.route_template for d in recorder.decisions} == {"/echo"}
    assert len(recorder.decisions) == 3


def test_route_label_falls_back_to_constant_without_policy_match(
    fake_redis: FakeRedis,
) -> None:
    recorder = _Recorder()
    client = make_client(decision_recorder=recorder)

    client.post("/echo", json={"v": 1})
    client.post("/other", json={"v": 1})

    assert {d.route_template for d in recorder.decisions} == {"<default>"}


def test_recorder_failure_does_not_break_the_request(
    fake_redis: FakeRedis,
) -> None:
    def exploding_recorder(decision: IdempotencyDecision) -> None:
        raise RuntimeError("recorder is broken")

    client = make_client(decision_recorder=exploding_recorder)

    response = client.post("/echo", json={"v": 1}, headers={"Idempotency-Key": "k"})

    assert response.status_code == 200
    assert _counter == 1


def test_no_recorder_configured_is_safe(fake_redis: FakeRedis) -> None:
    client = make_client()

    response = client.post("/echo", json={"v": 1}, headers={"Idempotency-Key": "k"})

    assert response.status_code == 200


# --- T5: structured logging on every decision --------------------------------


def _records(caplog: pytest.LogCaptureFixture, event: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "event", None) == event]


def test_decision_log_carries_event_status_and_request_id(
    fake_redis: FakeRedis,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One info record per decision, correlated with the caller's own
    X-Request-ID so the log ties to the response envelope."""
    client = make_client()
    with caplog.at_level(logging.INFO, logger="idempotency.middleware"):
        client.post(
            "/echo",
            json={"v": 1},
            headers={"Idempotency-Key": "k", "X-Request-ID": "rid-1"},
        )
        client.post(
            "/echo",
            json={"v": 1},
            headers={"Idempotency-Key": "k", "X-Request-ID": "rid-1"},
        )

    decisions = _records(caplog, "idempotency.decision")
    assert [r.outcome for r in decisions] == ["executed", "replayed"]
    assert all(r.status == "ok" for r in decisions)
    assert all(r.request_id == "rid-1" for r in decisions)


def test_rejected_decisions_log_rejected_status(
    fake_redis: FakeRedis,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = make_client()
    with caplog.at_level(logging.INFO, logger="idempotency.middleware"):
        client.post("/required")
        client.post(
            "/echo",
            json={"v": 1},
            headers={"Idempotency-Key": "bad key!"},
        )

    decisions = _records(caplog, "idempotency.decision")
    assert [r.outcome for r in decisions] == ["key_required", "key_invalid"]
    assert all(r.status == "rejected" for r in decisions)


def test_store_unavailable_logs_a_warning_not_a_decision(
    fake_redis: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = make_client()

    async def fail(config: IdempotencyConfig) -> FakeRedis:
        raise redis.exceptions.RedisError("down")

    monkeypatch.setattr(AsyncRedisPool, "connect", fail)
    with caplog.at_level(logging.INFO, logger="idempotency.middleware"):
        client.post("/required", json={"v": 1}, headers={"Idempotency-Key": "k"})

    warnings = _records(caplog, "idempotency.store_unavailable")
    assert len(warnings) == 1
    assert warnings[0].status == "failed"
    assert warnings[0].error_code == "dependency.connection_failed"
    assert warnings[0].request_id
    # The decision itself must not double-log at info.
    assert not _records(caplog, "idempotency.decision")


def test_principal_extractor_failure_rises_to_warning(
    fake_redis: FakeRedis,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def broken(request: Request) -> str:
        raise RuntimeError("auth backend down")

    client = make_client(principal_extractor=broken)
    with caplog.at_level(logging.INFO, logger="idempotency.middleware"):
        client.post("/echo", json={"v": 1}, headers={"Idempotency-Key": "k"})

    failures = _records(caplog, "idempotency.principal_extractor_failed")
    assert len(failures) == 1
    assert failures[0].levelno == logging.WARNING
    assert failures[0].status == "degraded"
    assert failures[0].error_code == "idempotency_principal_extractor_failed"
