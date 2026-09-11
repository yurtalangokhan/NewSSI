"""Endpoint-level validation of idempotency modes on real rag-service routes.

These tests exercise the IdempotencyMiddleware against the actual FastAPI app
(through the ASGI test client with the fake Redis store) to confirm each
idempotency mode is enforced on the endpoints it is configured for:

- EXCLUDED: health routes bypass idempotency entirely.
- OPTIONAL_REPLAY: mutating routes accept a missing key and replay with a key.
- REQUIRED_REPLAY: mutating routes reject a missing key (400) and replay.
- DOMAIN_REQUIRED: mutating routes reject a missing key (400) and replay.
"""

from tests.unit_tests.fixtures import get_async_test_client

USER_1_HEADERS = {"Authorization": "Bearer user1"}


def _keyed(headers: dict[str, str], key: str) -> dict[str, str]:
    return {**headers, "Idempotency-Key": key}


async def test_excluded_health_route_bypasses_idempotency() -> None:
    """EXCLUDED health routes never require a key and are not replayed."""
    async with get_async_test_client() as client:
        r1 = await client.get("/api/v1/health")
        r2 = await client.get("/api/v1/health")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert "Idempotency-Replayed" not in r1.headers
        assert "Idempotency-Replayed" not in r2.headers


async def test_required_replay_collection_create_rejects_missing_key() -> None:
    """REQUIRED_REPLAY POST /collections returns 400 without a key."""
    async with get_async_test_client() as client:
        r = await client.post(
            "/api/v1/collections",
            json={"name": "no-key", "metadata": {}},
            headers=USER_1_HEADERS,
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "idempotency_key_required"


async def test_required_replay_collection_create_replays_with_same_key() -> None:
    """REQUIRED_REPLAY POST /collections replays the cached response."""
    async with get_async_test_client() as client:
        payload = {"name": "replay-col", "metadata": {}}
        r1 = await client.post(
            "/api/v1/collections",
            json=payload,
            headers=_keyed(USER_1_HEADERS, "req-replay-col"),
        )
        assert r1.status_code == 201
        r2 = await client.post(
            "/api/v1/collections",
            json=payload,
            headers=_keyed(USER_1_HEADERS, "req-replay-col"),
        )
        assert r2.status_code == 201
        assert r2.headers.get("Idempotency-Replayed") == "true"
        assert r1.json()["uuid"] == r2.json()["uuid"]


async def test_required_replay_collection_create_conflicts_on_different_body() -> None:
    """REQUIRED_REPLAY POST /collections conflicts when body differs."""
    async with get_async_test_client() as client:
        r1 = await client.post(
            "/api/v1/collections",
            json={"name": "conflict-a", "metadata": {}},
            headers=_keyed(USER_1_HEADERS, "req-conflict-col"),
        )
        assert r1.status_code == 201
        r2 = await client.post(
            "/api/v1/collections",
            json={"name": "conflict-b", "metadata": {}},
            headers=_keyed(USER_1_HEADERS, "req-conflict-col"),
        )
        assert r2.status_code == 409
        assert r2.json()["error"]["code"] == "idempotency_key_reused"


async def test_domain_required_graph_build_rejects_missing_key() -> None:
    """DOMAIN_REQUIRED POST /graph/build returns 400 without a key."""
    async with get_async_test_client() as client:
        r = await client.post(
            "/api/v1/graph/build",
            json={"collection_id": "12345678-1234-5678-1234-567812345678"},
            headers=USER_1_HEADERS,
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "idempotency_key_required"


async def test_domain_required_upload_jobs_rejects_missing_key() -> None:
    """DOMAIN_REQUIRED POST /collections/{id}/documents/upload-jobs returns 400 without a key.

    Upload-jobs starts a background upload job and is high-risk; it must require
    an idempotency key to prevent duplicate job initialization.
    """
    async with get_async_test_client() as client:
        # Use a valid UUID for the collection_id - the idempotency middleware
        # rejects before route handler is reached.
        r = await client.post(
            "/api/v1/collections/12345678-1234-5678-1234-567812345678/documents/upload-jobs",
            files=[("files", ("test.txt", b"hello", "text/plain"))],
            headers=USER_1_HEADERS,
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "idempotency_key_required"


async def test_optional_replay_search_accepts_missing_key() -> None:
    """OPTIONAL_REPLAY POST /graph/search accepts a missing key."""
    async with get_async_test_client() as client:
        r = await client.post(
            "/api/v1/graph/search",
            json={
                "query": "q",
                "collection_id": "12345678-1234-5678-1234-567812345678",
            },
            headers=USER_1_HEADERS,
        )
        # Missing key is allowed; the request proceeds to route handling.
        assert r.status_code == 200
        assert "Idempotency-Replayed" not in r.headers


async def test_optional_replay_search_replays_with_same_key() -> None:
    """OPTIONAL_REPLAY POST /graph/search replays a cached response."""
    async with get_async_test_client() as client:
        payload = {
            "query": "q",
            "collection_id": "12345678-1234-5678-1234-567812345678",
        }
        r1 = await client.post(
            "/api/v1/graph/search",
            json=payload,
            headers=_keyed(USER_1_HEADERS, "opt-replay-search"),
        )
        r2 = await client.post(
            "/api/v1/graph/search",
            json=payload,
            headers=_keyed(USER_1_HEADERS, "opt-replay-search"),
        )
        assert r1.status_code == r2.status_code
        assert r2.headers.get("Idempotency-Replayed") == "true"
