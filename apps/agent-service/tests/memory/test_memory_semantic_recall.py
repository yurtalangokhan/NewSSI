"""Spec: recall must be query-aware, not a static "always show the same
facts" dump. Before this, recall_memories fetched a flat, capped list of
the user's most recent facts unconditionally on every turn -- a user with
any stored facts saw the "memories recalled" indicator on every message
regardless of whether the message had anything to do with those facts.

recall_memories now calls rag-service's semantic search
(integrations.rag_client.search_memory_facts) with the current message as the
query, so only facts actually relevant to *this* turn come back.
"""

import asyncio

import pytest

import memory.long_term as lt


@pytest.mark.asyncio
async def test_recall_memories_searches_with_the_given_query(monkeypatch):
    captured = {}

    async def _fake_search(user_id, query, *, limit=5):
        captured["user_id"] = user_id
        captured["query"] = query
        captured["limit"] = limit
        return []

    monkeypatch.setattr(lt, "search_memory_facts", _fake_search)

    await lt.recall_memories("user-1", "what do I like to drink")

    assert captured["user_id"] == "user-1"
    assert captured["query"] == "what do I like to drink"


@pytest.mark.asyncio
async def test_recall_memories_returns_only_the_matched_fact_content(monkeypatch):
    from integrations.rag_client import MemoryFactHit

    async def _fake_search(user_id, query, *, limit=5):
        return [
            MemoryFactHit(fact_id="f1", content="User likes tea", score=0.9),
            MemoryFactHit(fact_id="f2", content="User is a backend engineer", score=0.7),
        ]

    monkeypatch.setattr(lt, "search_memory_facts", _fake_search)

    memories = await lt.recall_memories("user-1", "what do I drink")

    assert memories == {"user_facts": ["User likes tea", "User is a backend engineer"]}


@pytest.mark.asyncio
async def test_recall_memories_with_no_matches_returns_empty(monkeypatch):
    async def _fake_search(user_id, query, *, limit=5):
        return []

    monkeypatch.setattr(lt, "search_memory_facts", _fake_search)

    memories = await lt.recall_memories("user-1", "unrelated message")

    assert memories == {}


@pytest.mark.asyncio
async def test_recall_memories_with_a_blank_query_does_not_call_search(monkeypatch):
    called = False

    async def _fake_search(user_id, query, *, limit=5):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(lt, "search_memory_facts", _fake_search)

    memories = await lt.recall_memories("user-1", "   ")

    assert memories == {}
    assert called is False


@pytest.mark.asyncio
async def test_recall_memories_without_a_user_id_does_not_call_search(monkeypatch):
    called = False

    async def _fake_search(user_id, query, *, limit=5):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(lt, "search_memory_facts", _fake_search)

    memories = await lt.recall_memories("", "some message")

    assert memories == {}
    assert called is False


@pytest.mark.asyncio
async def test_recall_memories_invokes_on_recall_when_facts_are_found(monkeypatch):
    from integrations.rag_client import MemoryFactHit

    async def _fake_search(user_id, query, *, limit=5):
        return [MemoryFactHit(fact_id="f1", content="User likes tea", score=0.9)]

    monkeypatch.setattr(lt, "search_memory_facts", _fake_search)

    recalled_payloads = []

    async def _on_recall(payload):
        recalled_payloads.append(payload)

    await lt.recall_memories("user-1", "drinks", on_recall=_on_recall)

    assert recalled_payloads == [{"fact_count": 1, "memories": ["User likes tea"]}]


@pytest.mark.asyncio
async def test_recall_memories_fails_open_when_search_raises(monkeypatch):
    async def _fake_search(user_id, query, *, limit=5):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(lt, "search_memory_facts", _fake_search)

    memories = await asyncio.wait_for(
        lt.recall_memories("user-1", "some message"), timeout=1.0
    )

    assert memories == {}
