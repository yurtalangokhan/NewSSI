"""Tests for src.memory.repository -- the only module that opens a
Milvus connection or embeds text for user facts. Mirrors the fake-store
style test_vectorstore_reuse.py and documents/service.py's own tests use.
"""

from __future__ import annotations

import pytest
from error_contract import DependencyUnavailableError
from langchain_core.documents import Document

from src.memory import repository


class _FakeStore:
    def __init__(self) -> None:
        self._metadata_field = "metadata"
        self.added_documents: list[Document] = []
        self.delete_exprs: list[str] = []
        self.search_calls: list[dict] = []
        self.search_results: list[tuple[Document, float]] = []
        self.raise_on_add: Exception | None = None
        self.raise_on_delete: Exception | None = None
        self.raise_on_search: Exception | None = None

    def add_documents(self, documents: list[Document]) -> list[str]:
        if self.raise_on_add:
            raise self.raise_on_add
        self.added_documents.extend(documents)
        return [f"id-{i}" for i in range(len(documents))]

    def delete(self, *, expr: str) -> None:
        if self.raise_on_delete:
            raise self.raise_on_delete
        self.delete_exprs.append(expr)

    def similarity_search_with_score(self, query: str, *, k: int, expr: str):
        if self.raise_on_search:
            raise self.raise_on_search
        self.search_calls.append({"query": query, "k": k, "expr": expr})
        return self.search_results


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _FakeStore:
    fake = _FakeStore()
    monkeypatch.setattr(repository, "_get_store", lambda: fake)
    return fake


async def test_upsert_embeds_and_stores_the_fact_with_user_and_fact_id_metadata(store):
    await repository.upsert_fact(user_id="user-1", fact_id="fact-1", content="User likes tea")

    assert len(store.added_documents) == 1
    doc = store.added_documents[0]
    assert doc.page_content == "User likes tea"
    assert doc.metadata == {"user_id": "user-1", "fact_id": "fact-1"}


async def test_upsert_raises_a_dependency_error_on_milvus_failure(store):
    store.raise_on_add = RuntimeError("connection refused")

    with pytest.raises(DependencyUnavailableError):
        await repository.upsert_fact(user_id="user-1", fact_id="fact-1", content="x")


async def test_delete_fact_deletes_by_user_and_fact_id(store):
    await repository.delete_fact(user_id="user-1", fact_id="fact-1")

    assert len(store.delete_exprs) == 1
    expr = store.delete_exprs[0]
    assert '"user-1"' in expr
    assert '"fact-1"' in expr


async def test_delete_fact_raises_a_dependency_error_on_milvus_failure(store):
    store.raise_on_delete = RuntimeError("timeout")

    with pytest.raises(DependencyUnavailableError):
        await repository.delete_fact(user_id="user-1", fact_id="fact-1")


async def test_delete_all_facts_deletes_by_user_id_only(store):
    await repository.delete_all_facts(user_id="user-1")

    assert len(store.delete_exprs) == 1
    expr = store.delete_exprs[0]
    assert '"user-1"' in expr
    assert "fact_id" not in expr


async def test_delete_all_facts_raises_a_dependency_error_on_milvus_failure(store):
    store.raise_on_delete = RuntimeError("timeout")

    with pytest.raises(DependencyUnavailableError):
        await repository.delete_all_facts(user_id="user-1")


async def test_search_returns_hits_scoped_to_the_user(store):
    store.search_results = [
        (Document(page_content="User likes tea", metadata={"fact_id": "f1"}), 0.9),
        (Document(page_content="User likes coffee", metadata={"fact_id": "f2"}), 0.4),
    ]

    hits = await repository.search_facts(user_id="user-1", query="drinks", limit=5)

    assert len(hits) == 2
    assert hits[0].fact_id == "f1"
    assert hits[0].content == "User likes tea"
    assert hits[0].score == 0.9
    assert store.search_calls[0]["k"] == 5
    assert '"user-1"' in store.search_calls[0]["expr"]


async def test_search_fails_open_to_empty_on_milvus_failure(store):
    # Unlike writes, search failures must never surface as an error -- a
    # chat turn degrades to "no recalled memories", it never breaks.
    store.raise_on_search = RuntimeError("connection refused")

    hits = await repository.search_facts(user_id="user-1", query="q", limit=5)

    assert hits == ()


async def test_search_skips_a_hit_missing_fact_id_metadata_rather_than_crashing(store):
    store.search_results = [(Document(page_content="orphan", metadata={}), 0.9)]

    hits = await repository.search_facts(user_id="user-1", query="q", limit=5)

    assert hits == ()
