"""Tests for ``ScalableGraphRepository``'s mode dispatch — previously untested.

Unlike the repositories it composes (covered by their own test files), this
class's own logic is *which* combination of calls to make for a given mode,
not raw Neo4j queries -- so it's tested by mocking ``_cluster``/``_expansion``/
``_stats_repo`` directly rather than a Neo4j session.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.graph.repositories.scalable_graph_repository import (
    ScalableGraphRepository,
)
from src.graph.schemas import GraphData, GraphNode, GraphStats


class _FakeResult:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        return self._iter()

    async def _iter(self):
        for record in self._records:
            yield record


class _FakeSession:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records
        self.calls: list[dict[str, Any]] = []

    async def run(self, query: Any, **params: Any) -> _FakeResult:
        self.calls.append(params)
        return _FakeResult(self._records)


def _stats(node_count: int = 100, edge_count: int = 200) -> GraphStats:
    return GraphStats(collection_id="col-1", node_count=node_count, edge_count=edge_count)


def _repo(monkeypatch, *, stats: GraphStats | None = None) -> ScalableGraphRepository:
    repo = ScalableGraphRepository("col-1")
    repo._stats_repo = AsyncMock(get_stats=AsyncMock(return_value=stats or _stats()))
    repo._cluster = AsyncMock()
    repo._expansion = AsyncMock()
    return repo


# ---------------------------------------------------------------------------
# get_scalable_graph_data — mode dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_mode_picks_full_for_a_small_graph(monkeypatch):
    repo = _repo(monkeypatch, stats=_stats(node_count=10))
    repo._expansion.get_important_nodes = AsyncMock(return_value=[])

    result = await repo.get_scalable_graph_data(mode="auto", node_limit=500)

    assert result.mode == "full"
    repo._cluster.get_graph_overview_with_edges.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_mode_picks_overview_for_a_large_graph(monkeypatch):
    repo = _repo(monkeypatch, stats=_stats(node_count=10_000))
    repo._cluster.get_graph_overview_with_edges = AsyncMock(
        return_value="overview-result"
    )

    result = await repo.get_scalable_graph_data(mode="auto", node_limit=500)

    assert result == "overview-result"
    repo._cluster.get_graph_overview_with_edges.assert_awaited_once_with(
        max_clusters=500
    )


@pytest.mark.asyncio
async def test_explicit_overview_mode_ignores_graph_size(monkeypatch):
    repo = _repo(monkeypatch, stats=_stats(node_count=1))
    repo._cluster.get_graph_overview_with_edges = AsyncMock(return_value="ov")

    result = await repo.get_scalable_graph_data(mode="overview", node_limit=500)

    assert result == "ov"


@pytest.mark.asyncio
async def test_expand_mode_without_a_cluster_label_falls_through_to_full(monkeypatch):
    repo = _repo(monkeypatch)
    repo._expansion.get_important_nodes = AsyncMock(return_value=[])

    result = await repo.get_scalable_graph_data(mode="expand", cluster_label=None)

    assert result.mode == "full"


@pytest.mark.asyncio
async def test_neighborhood_mode_without_a_node_id_falls_through_to_full(monkeypatch):
    repo = _repo(monkeypatch)
    repo._expansion.get_important_nodes = AsyncMock(return_value=[])

    result = await repo.get_scalable_graph_data(mode="neighborhood", node_id=None)

    assert result.mode == "full"


@pytest.mark.asyncio
async def test_neighborhood_mode_wraps_expansion_data_with_totals_from_stats(
    monkeypatch,
):
    repo = _repo(monkeypatch, stats=_stats(node_count=999, edge_count=888))
    node = GraphNode(id="n1", label="Person", name="Alice", properties={})
    repo._expansion.get_neighborhood = AsyncMock(
        return_value=GraphData(nodes=[node], edges=[])
    )

    result = await repo.get_scalable_graph_data(
        mode="neighborhood", node_id="n1", depth=2, node_limit=50
    )

    assert result.mode == "neighborhood"
    assert result.nodes == [node]
    assert result.total_node_count == 999
    assert result.total_edge_count == 888
    repo._expansion.get_neighborhood.assert_awaited_once_with("n1", depth=2, limit=50)


# ---------------------------------------------------------------------------
# _handle_expand — subcluster drill-down vs flat expand vs paginated expand
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expand_mode_drills_into_a_subcluster_id(monkeypatch):
    repo = _repo(monkeypatch)
    repo._expansion.expand_cluster_slice = AsyncMock(
        return_value=GraphData(nodes=[], edges=[])
    )
    repo._expansion.get_label_metadata = AsyncMock(return_value=({}, {}))

    result = await repo.get_scalable_graph_data(
        mode="expand",
        cluster_label="subcluster__Person__100__50",
        edge_limit=500,
    )

    assert result.mode == "expand"
    assert result.scope_label == "Person"
    assert result.metadata["scope_skip"] == 100
    assert result.metadata["scope_limit"] == 50
    repo._expansion.expand_cluster_slice.assert_awaited_once_with(
        "Person", skip=100, limit=50, edge_limit=500
    )


@pytest.mark.asyncio
async def test_expand_mode_returns_flat_nodes_when_label_is_small_enough(monkeypatch):
    repo = _repo(monkeypatch)
    repo._expansion.count_label_nodes = AsyncMock(return_value=10)
    node = GraphNode(id="n1", label="Person", name="Alice", properties={})
    repo._expansion.expand_cluster = AsyncMock(
        return_value=GraphData(nodes=[node], edges=[])
    )
    repo._expansion.get_label_metadata = AsyncMock(
        return_value=({"WORKS_AT": 3}, {"Company": 2})
    )

    result = await repo.get_scalable_graph_data(
        mode="expand", cluster_label="Person", node_limit=200
    )

    assert result.mode == "expand"
    assert result.nodes == [node]
    assert result.scope_label == "Person"
    assert result.metadata["rel_type_counts"] == {"WORKS_AT": 3}
    repo._expansion.expand_cluster.assert_awaited_once()


@pytest.mark.asyncio
async def test_expand_mode_produces_subclusters_when_label_exceeds_node_limit(
    monkeypatch,
):
    repo = _repo(monkeypatch)
    repo._expansion.count_label_nodes = AsyncMock(return_value=1000)
    repo._expansion.top_entity_names = AsyncMock(return_value=[f"n{i}" for i in range(1000)])
    repo._expansion.count_label_edges = AsyncMock(return_value=50)
    repo._expansion.get_label_metadata = AsyncMock(return_value=({}, {"Company": 5}))
    repo._expansion.get_chunked_internal_rel_types = AsyncMock(
        return_value={0: {"WORKS_AT": 3}}
    )

    result = await repo.get_scalable_graph_data(
        mode="expand", cluster_label="Person", node_limit=200
    )

    assert result.mode == "expand"
    assert result.cluster_count == len(result.nodes)
    assert result.total_node_count == 1000
    assert result.total_edge_count == 50
    # Each sub-cluster is annotated with its own chunk's rel-type counts and
    # the shared neighbor-label counts.
    first = result.nodes[0]
    assert first.properties["_rel_type_counts"] == {"WORKS_AT": 3}
    assert first.properties["_neighbor_label_counts"] == {"Company": 5}


# ---------------------------------------------------------------------------
# _handle_full_mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_mode_skips_edge_query_when_there_are_no_important_nodes(
    monkeypatch,
):
    repo = _repo(monkeypatch)
    repo._expansion.get_important_nodes = AsyncMock(return_value=[])
    session = _FakeSession([])

    @asynccontextmanager
    async def _session(self, **_kwargs):
        yield session

    monkeypatch.setattr(ScalableGraphRepository, "_session", _session)

    result = await repo.get_scalable_graph_data(mode="full")

    assert result.nodes == []
    assert result.edges == []
    assert session.calls == []  # never opened a session for zero node ids


@pytest.mark.asyncio
async def test_full_mode_fetches_edges_for_the_important_node_ids(monkeypatch):
    repo = _repo(monkeypatch)
    node = GraphNode(id="n1", label="Person", name="Alice", properties={})
    repo._expansion.get_important_nodes = AsyncMock(return_value=[node])
    edge_records = [
        {"id": "e1", "src": "n1", "tgt": "n1", "rtype": "SELF", "props": {}},
    ]
    session = _FakeSession(edge_records)

    @asynccontextmanager
    async def _session(self, **_kwargs):
        yield session

    monkeypatch.setattr(ScalableGraphRepository, "_session", _session)

    result = await repo.get_scalable_graph_data(mode="full", edge_limit=250)

    assert result.nodes == [node]
    assert len(result.edges) == 1
    assert session.calls[0]["ids"] == ["n1"]
    assert session.calls[0]["limit"] == 250
