"""Spec: UserMemoryService's only remaining job is persisting
auto-extracted facts through user-service. Recall moved to
memory.long_term.recall_memories (semantic search via rag-service) and
manual CRUD is served directly by user-service's own public API -- neither
runs through this service or any agent-service-side cache anymore, so the
LangGraph-Store-backed LongTermMemoryCache this class used to own is gone.
"""

from unittest.mock import AsyncMock

import pytest

from service.user_memory.user_memory_service import UserMemoryService


@pytest.mark.asyncio
async def test_add_facts_dedupes_case_insensitively_before_calling_user_service(monkeypatch):
    add_facts_to_user = AsyncMock(return_value=[{"id": "1", "content": "User likes tea"}])
    monkeypatch.setattr(
        "service.user_memory.user_memory_service.add_facts_to_user", add_facts_to_user
    )

    service = UserMemoryService()
    result = await service.add_facts("user-1", ["User likes tea", "user likes tea", "  "])

    add_facts_to_user.assert_awaited_once_with(
        "user-1", ["User likes tea"], source="auto_extracted", language=""
    )
    assert result == [{"id": "1", "content": "User likes tea"}]


@pytest.mark.asyncio
async def test_add_facts_with_no_contents_does_not_call_user_service(monkeypatch):
    add_facts_to_user = AsyncMock()
    monkeypatch.setattr(
        "service.user_memory.user_memory_service.add_facts_to_user", add_facts_to_user
    )

    service = UserMemoryService()
    result = await service.add_facts("user-1", [])

    assert result == []
    add_facts_to_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_facts_passes_through_a_custom_source(monkeypatch):
    add_facts_to_user = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "service.user_memory.user_memory_service.add_facts_to_user", add_facts_to_user
    )

    service = UserMemoryService()
    await service.add_facts("user-1", ["fact"], source="manual")

    add_facts_to_user.assert_awaited_once_with(
        "user-1", ["fact"], source="manual", language=""
    )


@pytest.mark.asyncio
async def test_add_facts_forwards_the_language_the_extractor_declared(monkeypatch):
    """The extractor's model names the user's language in its structured
    answer; that tag has to reach user-service or a wrong-language fact stays
    undetectable -- recall simply never matches it, and nothing records why."""
    add_facts_to_user = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "service.user_memory.user_memory_service.add_facts_to_user", add_facts_to_user
    )

    service = UserMemoryService()
    await service.add_facts("user-1", ["用户住在开塞利。"], language="zh-Hans")

    add_facts_to_user.assert_awaited_once_with(
        "user-1", ["用户住在开塞利。"], source="auto_extracted", language="zh-Hans"
    )


def test_service_no_longer_exposes_the_cache_backed_recall_and_crud_methods():
    # Confirms the cleanup: these all used to route through
    # LongTermMemoryCache, which no longer exists.
    for removed in ("list_for_recall", "list_for_ui", "create", "update", "delete", "delete_all"):
        assert not hasattr(UserMemoryService, removed)


def test_get_user_memory_service_returns_a_singleton():
    from service.user_memory.user_memory_service import get_user_memory_service

    first = get_user_memory_service()
    second = get_user_memory_service()

    assert first is second
