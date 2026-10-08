"""Tests for ``StatsRepository`` — previously untested graph statistics logic.

Follows the established ``_session`` monkeypatch pattern (see
``test_entity_bulk_upsert_batching.py``): the repository's Neo4j session is
replaced with a fake that records queries and serves canned records, so
these run without a live Neo4j. ``list_graph_collection_ids`` bypasses
``_session`` and calls ``get_neo4j_driver()`` directly, so it gets its own
fake driver.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

from src.graph.repositories import stats_repository as stats_module
from src.graph.repositories.stats_repository import StatsRepository


class _FakeResult:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        return self._iter()

    async def _iter(self):
        for record in self._records:
            yield record

    async def single(self) -> dict[str, Any] | None:
        return self._records[0] if self._records else None


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
    async def _session(self: StatsRepository, **_kwargs: Any):
        yield session

    monkeypatch.setattr(StatsRepository, "_session", _session)
    return StatsRepository("col-1"), session


# ---------------------------------------------------------------------------
# list_graph_collection_ids — bypasses _session, talks to the driver directly
# ---------------------------------------------------------------------------


def _fake_driver(session: _FakeSession):
    class _Driver:
        def session(self):
            @asynccontextmanager
            async def _cm():
                yield session

            return _cm()

    return _Driver()


@pytest.mark.asyncio
async def test_list_graph_collection_ids_returns_distinct_ids(monkeypatch):
    session = _FakeSession([[{"cid": "col-1"}, {"cid": "col-2"}]])

    async def fake_get_driver():
        return _fake_driver(session)

    monkeypatch.setattr(stats_module, "get_neo4j_driver", fake_get_driver)

    ids = await StatsRepository.list_graph_collection_ids()

    assert ids == ["col-1", "col-2"]
    assert session.calls[0][0] is stats_module.LIST_GRAPH_COLLECTION_IDS


@pytest.mark.asyncio
async def test_list_graph_collection_ids_filters_out_falsy_cids(monkeypatch):
    session = _FakeSession([[{"cid": "col-1"}, {"cid": None}, {"cid": ""}]])

    async def fake_get_driver():
        return _fake_driver(session)

    monkeypatch.setattr(stats_module, "get_neo4j_driver", fake_get_driver)

    ids = await StatsRepository.list_graph_collection_ids()

    assert ids == ["col-1"]


# ---------------------------------------------------------------------------
# get_stats — global (unscoped)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stats_global_aggregates_counts_from_label_and_rel_results(
    monkeypatch,
):
    repo, session = _repo(
        monkeypatch,
        [
            [{"label": "Person", "cnt": 3}, {"label": "Org", "cnt": 2}],
            [{"rtype": "WORKS_AT", "cnt": 4}],
        ],
    )

    stats = await repo.get_stats()

    assert stats.node_count == 5
    assert stats.edge_count == 4
    assert stats.label_counts == {"Person": 3, "Org": 2}
    assert stats.relationship_type_counts == {"WORKS_AT": 4}
    assert session.calls[0][0] is stats_module.LABEL_COUNTS
    assert session.calls[1][0] is stats_module.RELATIONSHIP_TYPE_COUNTS


@pytest.mark.asyncio
async def test_get_stats_global_falls_back_to_entity_for_missing_label(monkeypatch):
    repo, _session = _repo(
        monkeypatch,
        [
            [{"label": None, "cnt": 1}],
            [],
        ],
    )

    stats = await repo.get_stats()

    assert stats.label_counts == {"Entity": 1}
    assert stats.node_count == 1


# ---------------------------------------------------------------------------
# get_stats — scoped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stats_scoped_runs_four_scoped_queries_with_scope_label(monkeypatch):
    repo, session = _repo(
        monkeypatch,
        [
            [{"cnt": 7}],  # node count
            [{"cnt": 9}],  # edge count
            [{"label": "Org", "cnt": 2}],  # label breakdown
            [{"rtype": "MEMBER_OF", "cnt": 6}],  # rel type breakdown
        ],
    )

    stats = await repo.get_stats(scope_label="Person")

    assert stats.node_count == 7
    assert stats.edge_count == 9
    assert stats.label_counts == {"Org": 2}
    assert stats.relationship_type_counts == {"MEMBER_OF": 6}
    assert session.calls[0][0] is stats_module.NODE_COUNT_SCOPED
    assert session.calls[0][1]["scope_label"] == "Person"
    assert session.calls[1][0] is stats_module.EDGE_COUNT_SCOPED
    assert session.calls[2][0] is stats_module.LABEL_COUNTS_SCOPED
    assert session.calls[3][0] is stats_module.RELATIONSHIP_TYPE_COUNTS_SCOPED


@pytest.mark.asyncio
async def test_get_stats_scoped_defaults_to_zero_when_single_returns_none(monkeypatch):
    repo, _session = _repo(monkeypatch, [[], [], [], []])

    stats = await repo.get_stats(scope_label="Ghost")

    assert stats.node_count == 0
    assert stats.edge_count == 0


# ---------------------------------------------------------------------------
# get_labels_paginated — branch selection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_labels_paginated_unscoped_no_filters(monkeypatch):
    repo, session = _repo(
        monkeypatch, [[{"label": "Person", "cnt": 3}, {"label": "Org", "cnt": 1}]]
    )

    result = await repo.get_labels_paginated()

    assert session.calls[0][0] is stats_module.LABELS_PAGINATED_UNSCOPED
    assert result.total == 2
    assert result.items == [
        {"name": "Person", "count": 3},
        {"name": "Org", "count": 1},
    ]


@pytest.mark.asyncio
async def test_get_labels_paginated_scoped_no_filters(monkeypatch):
    repo, session = _repo(monkeypatch, [[{"label": "Org", "cnt": 4}]])

    await repo.get_labels_paginated(scope_label="Person")

    assert session.calls[0][0] is stats_module.LABELS_PAGINATED_SCOPED
    assert session.calls[0][1]["scope_label"] == "Person"


@pytest.mark.asyncio
async def test_get_labels_paginated_with_rel_type_filter_unscoped(monkeypatch):
    repo, session = _repo(monkeypatch, [[{"label": "Person", "cnt": 1}]])

    await repo.get_labels_paginated(rel_type_filter=["WORKS_AT"])

    assert session.calls[0][0] is stats_module.LABELS_FILTERED_BY_REL_TYPES
    assert session.calls[0][1]["rel_types"] == ["WORKS_AT"]


@pytest.mark.asyncio
async def test_get_labels_paginated_with_rel_type_filter_and_scope_label(monkeypatch):
    """rel_type_filter takes priority over a bare scope_label branch."""
    repo, session = _repo(monkeypatch, [[{"label": "Org", "cnt": 1}]])

    await repo.get_labels_paginated(scope_label="Person", rel_type_filter=["MEMBER_OF"])

    assert session.calls[0][0] is stats_module.LABELS_SCOPED_FILTERED_BY_REL_TYPES
    assert session.calls[0][1]["scope_label"] == "Person"
    assert session.calls[0][1]["rel_types"] == ["MEMBER_OF"]


@pytest.mark.asyncio
async def test_get_labels_paginated_search_filter_is_case_insensitive(monkeypatch):
    repo, _session = _repo(
        monkeypatch, [[{"label": "Person", "cnt": 3}, {"label": "Org", "cnt": 1}]]
    )

    result = await repo.get_labels_paginated(search="PERS")

    assert result.total == 1
    assert result.items == [{"name": "Person", "count": 3}]


@pytest.mark.asyncio
async def test_get_labels_paginated_pagination_math_and_has_next(monkeypatch):
    records = [{"label": f"L{i}", "cnt": i} for i in range(5)]
    repo, _session = _repo(monkeypatch, [records])

    page1 = await repo.get_labels_paginated(page=1, page_size=2)
    assert len(page1.items) == 2
    assert page1.total == 5
    assert page1.has_next is True

    repo2, _session2 = _repo(monkeypatch, [records])
    page3 = await repo2.get_labels_paginated(page=3, page_size=2)
    assert len(page3.items) == 1
    assert page3.has_next is False


# ---------------------------------------------------------------------------
# get_relationship_types_paginated — branch selection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_relationship_types_paginated_unscoped_no_filters(monkeypatch):
    repo, session = _repo(monkeypatch, [[{"rtype": "WORKS_AT", "cnt": 3}]])

    await repo.get_relationship_types_paginated()

    assert session.calls[0][0] is stats_module.RELATIONSHIP_TYPES_PAGINATED_UNSCOPED


@pytest.mark.asyncio
async def test_get_relationship_types_paginated_scoped_no_filters(monkeypatch):
    repo, session = _repo(monkeypatch, [[{"rtype": "WORKS_AT", "cnt": 3}]])

    await repo.get_relationship_types_paginated(scope_label="Person")

    assert session.calls[0][0] is stats_module.RELATIONSHIP_TYPES_PAGINATED_SCOPED
    assert session.calls[0][1]["scope_label"] == "Person"


@pytest.mark.asyncio
async def test_get_relationship_types_paginated_chunk_scoped(monkeypatch):
    repo, session = _repo(monkeypatch, [[{"rtype": "WORKS_AT", "cnt": 2}]])

    await repo.get_relationship_types_paginated(
        scope_label="Person", scope_skip=10, scope_limit=5
    )

    assert session.calls[0][0] is stats_module.RELATIONSHIP_TYPES_CHUNK_SCOPED
    assert session.calls[0][1]["scope_skip"] == 10
    assert session.calls[0][1]["scope_end"] == 15


@pytest.mark.asyncio
async def test_get_relationship_types_paginated_chunk_scoped_takes_priority_over_label_filter(
    monkeypatch,
):
    """scope_skip/scope_limit win over label_filter when both are supplied."""
    repo, session = _repo(monkeypatch, [[{"rtype": "WORKS_AT", "cnt": 2}]])

    await repo.get_relationship_types_paginated(
        scope_label="Person",
        scope_skip=0,
        scope_limit=5,
        label_filter=["Org"],
    )

    assert session.calls[0][0] is stats_module.RELATIONSHIP_TYPES_CHUNK_SCOPED


@pytest.mark.asyncio
async def test_get_relationship_types_paginated_label_filter_unscoped(monkeypatch):
    repo, session = _repo(monkeypatch, [[{"rtype": "WORKS_AT", "cnt": 2}]])

    await repo.get_relationship_types_paginated(label_filter=["Person", "Org"])

    assert session.calls[0][0] is stats_module.REL_TYPES_FILTERED_BY_LABELS
    assert session.calls[0][1]["labels"] == ["Person", "Org"]


@pytest.mark.asyncio
async def test_get_relationship_types_paginated_label_filter_scoped(monkeypatch):
    repo, session = _repo(monkeypatch, [[{"rtype": "WORKS_AT", "cnt": 2}]])

    await repo.get_relationship_types_paginated(
        scope_label="Person", label_filter=["Org"]
    )

    assert session.calls[0][0] is stats_module.REL_TYPES_SCOPED_FILTERED_BY_LABELS


@pytest.mark.asyncio
async def test_get_relationship_types_paginated_search_filter(monkeypatch):
    repo, _session = _repo(
        monkeypatch,
        [[{"rtype": "WORKS_AT", "cnt": 3}, {"rtype": "MEMBER_OF", "cnt": 1}]],
    )

    result = await repo.get_relationship_types_paginated(search="works")

    assert result.total == 1
    assert result.items == [{"name": "WORKS_AT", "count": 3}]


@pytest.mark.asyncio
async def test_get_relationship_types_paginated_pagination_math(monkeypatch):
    records = [{"rtype": f"REL_{i}", "cnt": i} for i in range(3)]
    repo, _session = _repo(monkeypatch, [records])

    result = await repo.get_relationship_types_paginated(page=2, page_size=2)

    assert len(result.items) == 1
    assert result.has_next is False
