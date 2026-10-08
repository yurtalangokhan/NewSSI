"""Tests for ``SearchRepository`` — previously untested BM25/CONTAINS/context search.

Follows the established ``_session`` monkeypatch pattern (see
``test_entity_bulk_upsert_batching.py``): the repository's Neo4j session is
replaced with a fake that records queries and serves canned records, so
these run without a live Neo4j.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

from src.graph.repositories.search_repository import (
    SearchRepository,
    relationship_type_candidates,
)


class _FakeResult:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        return self._iter()

    async def _iter(self):
        for record in self._records:
            yield record


class _FakeSession:
    def __init__(self, results_by_call: list[list[dict[str, Any]]]) -> None:
        self._results_by_call = list(results_by_call)
        self.calls: list[tuple[Any, dict[str, Any]]] = []

    async def run(self, query: Any, **params: Any) -> _FakeResult:
        self.calls.append((query, params))
        records = self._results_by_call.pop(0) if self._results_by_call else []
        return _FakeResult(records)


def _repo(monkeypatch, results_by_call: list[list[dict[str, Any]]]):
    session = _FakeSession(results_by_call)

    @asynccontextmanager
    async def _session(self: SearchRepository, **_kwargs: Any):
        yield session

    monkeypatch.setattr(SearchRepository, "_session", _session)
    return SearchRepository("col-1"), session


# ---------------------------------------------------------------------------
# relationship_type_candidates — pure function, no Neo4j needed
# ---------------------------------------------------------------------------


def test_relationship_type_candidates_matches_turkish_alias():
    assert relationship_type_candidates("genel mudur kim") == ["GENERAL_MANAGER"]


def test_relationship_type_candidates_matches_english_alias():
    assert relationship_type_candidates("who is the general manager") == [
        "GENERAL_MANAGER"
    ]


def test_relationship_type_candidates_accepts_explicit_snake_case():
    assert relationship_type_candidates("GENERAL_MANAGER") == ["GENERAL_MANAGER"]


def test_relationship_type_candidates_empty_for_unrelated_query():
    assert relationship_type_candidates("what is the weather today") == []


def test_relationship_type_candidates_empty_for_blank_query():
    assert relationship_type_candidates("   ") == []


def test_relationship_type_candidates_deduplicates():
    # "GENERAL_MANAGER" independently matches both the snake_case check
    # (it contains "_") and the alias loop (its normalized form "general
    # manager" is itself one of GENERAL_MANAGER's aliases); the caller must
    # see it once, not twice.
    candidates = relationship_type_candidates("GENERAL_MANAGER")
    assert candidates == ["GENERAL_MANAGER"]


# ---------------------------------------------------------------------------
# _escape_lucene — pure static method
# ---------------------------------------------------------------------------


def test_escape_lucene_escapes_special_characters():
    escaped = SearchRepository._escape_lucene("a+b-c(d)")
    assert escaped == r"a\+b\-c\(d\)"


def test_escape_lucene_leaves_plain_text_untouched():
    assert SearchRepository._escape_lucene("plain text") == "plain text"


# ---------------------------------------------------------------------------
# search_entities_bm25
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_entities_bm25_returns_empty_for_blank_query(monkeypatch):
    repo, session = _repo(monkeypatch, [])
    assert await repo.search_entities_bm25("   ") == []
    assert session.calls == []


@pytest.mark.asyncio
async def test_search_entities_bm25_maps_nodes_and_scores(monkeypatch):
    records = [
        {
            "id": "n1",
            "label": "Entity",
            "name": "Alice",
            "props": {},
            "score": 3.5,
        }
    ]
    repo, session = _repo(monkeypatch, [records])

    results = await repo.search_entities_bm25("alice", limit=5)

    assert len(results) == 1
    assert results[0]["node"].name == "Alice"
    assert results[0]["bm25_score"] == 3.5
    # Lucene query built with fuzzy (~1) per token.
    _, params = session.calls[0]
    assert params["lucene_query"] == "alice~1"
    assert params["limit"] == 5


# ---------------------------------------------------------------------------
# fetch_subgraph_for_names
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_subgraph_for_names_short_circuits_on_empty_names(monkeypatch):
    repo, session = _repo(monkeypatch, [])
    result = await repo.fetch_subgraph_for_names([])
    assert result.nodes == []
    assert result.edges == []
    assert session.calls == []


@pytest.mark.asyncio
async def test_fetch_subgraph_for_names_returns_edges_with_both_endpoints(monkeypatch):
    records = [
        {
            "src_id": "a",
            "src_label": "Process",
            "src_name": "Annual Leave Carry-over",
            "src_props": {},
            "tgt_id": "b",
            "tgt_label": "Role",
            "tgt_name": "Line Manager",
            "tgt_props": {"scope": "direct reports"},
            "id": "e1",
            "rtype": "REQUIRES_APPROVAL_FROM",
            "props": {},
        },
        {
            "src_id": "a",
            "src_label": "Process",
            "src_name": "Annual Leave Carry-over",
            "src_props": {},
            "tgt_id": "c",
            "tgt_label": "Department",
            "tgt_name": "HR",
            "tgt_props": {},
            "id": "e2",
            "rtype": "OWNED_BY",
            "props": {},
        },
    ]
    repo, session = _repo(monkeypatch, [records])

    result = await repo.fetch_subgraph_for_names(["Annual Leave Carry-over"], limit=10)

    assert [node.id for node in result.nodes] == ["a", "b", "c"]
    assert [edge.type for edge in result.edges] == [
        "REQUIRES_APPROVAL_FROM",
        "OWNED_BY",
    ]
    assert [(edge.source, edge.target) for edge in result.edges] == [
        ("a", "b"),
        ("a", "c"),
    ]
    assert result.nodes[1].properties == {"scope": "direct reports"}
    _, params = session.calls[0]
    assert params["names"] == ["Annual Leave Carry-over"]
    assert params["limit"] == 10


# ---------------------------------------------------------------------------
# search_relationships_by_type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_relationships_by_type_short_circuits_when_no_candidates(
    monkeypatch,
):
    repo, session = _repo(monkeypatch, [])
    result = await repo.search_relationships_by_type("unrelated query text")
    assert result.nodes == []
    assert result.edges == []
    assert session.calls == []


@pytest.mark.asyncio
async def test_search_relationships_by_type_maps_source_and_target(monkeypatch):
    records = [
        {
            "src_id": "n1",
            "src_label": "Person",
            "src_name": "Alice",
            "src_props": {},
            "tgt_id": "n2",
            "tgt_label": "Company",
            "tgt_name": "Acme",
            "tgt_props": {},
            "id": "e1",
            "rtype": "GENERAL_MANAGER",
            "props": {},
        }
    ]
    repo, session = _repo(monkeypatch, [records])

    result = await repo.search_relationships_by_type("general manager")

    assert {n.name for n in result.nodes} == {"Alice", "Acme"}
    assert [(edge.source, edge.target) for edge in result.edges] == [("n1", "n2")]
    _, params = session.calls[0]
    assert params["relationship_types"] == ["GENERAL_MANAGER"]


# ---------------------------------------------------------------------------
# search_entity_clusters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_entity_clusters_returns_label_counts(monkeypatch):
    records = [{"label": "Person", "cnt": 3}, {"label": None, "cnt": 1}]
    repo, session = _repo(monkeypatch, [records])

    clusters = await repo.search_entity_clusters("alice")

    assert clusters == {"Person": 3, "Entity": 1}


@pytest.mark.asyncio
async def test_search_entity_clusters_builds_subcluster_ids_when_scoped(monkeypatch):
    records = [{"offset": 0, "cnt": 5}, {"offset": 200, "cnt": 2}]
    repo, session = _repo(monkeypatch, [records])

    clusters = await repo.search_entity_clusters(
        "alice", scope_label="Person", chunk_size=200
    )

    assert clusters == {
        "subcluster__Person__0__200": 5,
        "subcluster__Person__200__200": 2,
    }


# ---------------------------------------------------------------------------
# get_entity_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_entity_context_returns_empty_string_when_nothing_found(monkeypatch):
    repo, session = _repo(monkeypatch, [[]])
    assert await repo.get_entity_context(["alice"]) == ""


@pytest.mark.asyncio
async def test_get_entity_context_formats_and_deduplicates_lines(monkeypatch):
    records = [
        {"src": "Alice", "rtype": "WORKS_AT", "tgt": "Acme"},
        {"src": "Alice", "rtype": "WORKS_AT", "tgt": "Acme"},  # duplicate
    ]
    repo, session = _repo(monkeypatch, [records])

    context = await repo.get_entity_context(["alice"])

    assert context.count("Alice --[WORKS_AT]--> Acme") == 1
    assert context.startswith("Knowledge Graph Context:")


# ---------------------------------------------------------------------------
# get_entity_context_focused
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_entity_context_focused_empty_for_no_seed_entities(monkeypatch):
    repo, session = _repo(monkeypatch, [])
    assert await repo.get_entity_context_focused([]) == ""
    assert session.calls == []


@pytest.mark.asyncio
async def test_get_entity_context_focused_separates_direct_from_indirect(monkeypatch):
    records = [
        # Both endpoints are seeds -> direct.
        {"src": "Alice", "rtype": "WORKS_WITH", "tgt": "Bob"},
        # Only one endpoint is a seed -> indirect.
        {"src": "Alice", "rtype": "WORKS_AT", "tgt": "Acme"},
    ]
    repo, session = _repo(monkeypatch, [records])

    # Seed matching is case-sensitive against the record's src/tgt text.
    context = await repo.get_entity_context_focused(["Alice", "Bob"])

    assert "[Direct relationships]" in context
    assert "[Related entities]" in context
    direct_section, _, indirect_section = context.partition("[Related entities]")
    assert "Alice --[WORKS_WITH]--> Bob" in direct_section
    assert "Alice --[WORKS_AT]--> Acme" in indirect_section


@pytest.mark.asyncio
async def test_get_entity_context_focused_caps_indirect_lines(monkeypatch):
    records = [
        {"src": "alice", "rtype": "KNOWS", "tgt": f"person-{i}"} for i in range(10)
    ]
    repo, session = _repo(monkeypatch, [records])

    context = await repo.get_entity_context_focused(["alice"], max_indirect=3)

    # Only 3 of the 10 one-hop relationships should survive the cap.
    assert context.count("--[KNOWS]-->") == 3
