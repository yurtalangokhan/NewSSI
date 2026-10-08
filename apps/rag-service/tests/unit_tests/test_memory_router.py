"""HTTP/auth boundary tests for the memory-facts domain.

Mirrors test_retrieval_contract.py's style for the same trusted-delegation
pattern: internal-service callers must delegate a real end-user identity
via x-user-id, never act "as themselves" or with no identity at all.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.memory import repository as memory_repository
from src.shared import auth
from tests.unit_tests.fixtures import get_async_test_client


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", "internal-token")


def _headers(user_id: str | None = "member") -> dict[str, str]:
    headers = {"x-internal-token": "internal-token"}
    if user_id is not None:
        headers["x-user-id"] = user_id
    return headers


@pytest.mark.parametrize("delegated_user", [None, "", "   ", "internal-service", "dev-user"])
async def test_upsert_rejects_missing_or_reserved_delegated_user(monkeypatch, delegated_user):
    upsert = AsyncMock()
    monkeypatch.setattr(memory_repository, "upsert_fact", upsert)

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/memory/facts",
            json={"fact_id": "f1", "content": "User likes tea"},
            headers=_headers(delegated_user),
        )

    assert response.status_code == 403
    upsert.assert_not_awaited()


async def test_upsert_delegates_to_the_repository_for_the_trusted_user(monkeypatch):
    upsert = AsyncMock()
    monkeypatch.setattr(memory_repository, "upsert_fact", upsert)

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/memory/facts",
            json={"fact_id": "f1", "content": "User likes tea"},
            headers=_headers("member"),
        )

    assert response.status_code == 200
    upsert.assert_awaited_once_with(user_id="member", fact_id="f1", content="User likes tea")


async def test_delete_fact_delegates_to_the_repository(monkeypatch):
    delete = AsyncMock()
    monkeypatch.setattr(memory_repository, "delete_fact", delete)

    async with get_async_test_client() as client:
        response = await client.delete("/api/v1/memory/facts/f1", headers=_headers("member"))

    assert response.status_code == 200
    delete.assert_awaited_once_with(user_id="member", fact_id="f1")


async def test_delete_all_facts_delegates_to_the_repository(monkeypatch):
    delete_all = AsyncMock()
    monkeypatch.setattr(memory_repository, "delete_all_facts", delete_all)

    async with get_async_test_client() as client:
        response = await client.delete("/api/v1/memory/facts", headers=_headers("member"))

    assert response.status_code == 200
    delete_all.assert_awaited_once_with(user_id="member")


async def test_search_returns_hits_from_the_repository(monkeypatch):
    from src.memory.contract import MemoryFactHit

    search = AsyncMock(
        return_value=(MemoryFactHit(fact_id="f1", content="User likes tea", score=0.9),)
    )
    monkeypatch.setattr(memory_repository, "search_facts", search)

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/memory/search",
            json={"query": "what do I drink", "limit": 5},
            headers=_headers("member"),
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["hits"]) == 1
    assert body["hits"][0]["fact_id"] == "f1"
    assert body["hits"][0]["content"] == "User likes tea"
    # The repository port hands back a cosine; the service fuses it with the
    # lexical ranking, so the exposed score is the fused RRF value and the
    # cosine travels alongside it.
    assert body["hits"][0]["vector_score"] == 0.9
    assert body["hits"][0]["score"] > 0.0
    search.assert_awaited_once_with(user_id="member", query="what do I drink", limit=5)


async def test_search_rejects_a_delegated_internal_service_identity(monkeypatch):
    search = AsyncMock()
    monkeypatch.setattr(memory_repository, "search_facts", search)

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/memory/search",
            json={"query": "q"},
            headers=_headers("internal-service"),
        )

    assert response.status_code == 403
    search.assert_not_awaited()
