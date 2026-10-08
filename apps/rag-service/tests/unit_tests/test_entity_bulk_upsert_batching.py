"""Writing an extracted graph is a handful of round-trips, not one per element.

``bulk_upsert`` was a Python loop over ``upsert_node`` and ``upsert_edge``,
and each of those opened its own session and ran its own statement. A
document that extracted 200 entities and 400 relations therefore made 600
sequential round-trips to Neo4j, each paying full latency, and opened 600
sessions to do it -- while the ingestion request waited. The same work is
a single UNWIND per node batch and one per relationship type, because
relationship types are the only part that cannot be parameterised.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

from src.graph.repositories.entity_repository import EntityRepository


class _Result:
    def __init__(self, record: dict[str, Any] | None) -> None:
        self._record = record

    async def single(self) -> dict[str, Any] | None:
        return self._record


class _Session:
    def __init__(self, log: list[tuple[str, dict[str, Any]]]) -> None:
        self._log = log

    async def run(self, query: Any, **params: Any) -> _Result:
        text = getattr(query, "text", query)
        self._log.append((str(text), params))
        rows = params.get("rows") or []
        return _Result({"upserted": len(rows)})


def _repo(monkeypatch: pytest.MonkeyPatch) -> tuple[EntityRepository, list, list]:
    statements: list[tuple[str, dict[str, Any]]] = []
    sessions: list[_Session] = []

    @asynccontextmanager
    async def _session(self: EntityRepository, **_kwargs: Any):
        session = _Session(statements)
        sessions.append(session)
        yield session

    monkeypatch.setattr(EntityRepository, "_session", _session)
    return EntityRepository("col-1"), statements, sessions


def _entities(n: int) -> list[dict[str, Any]]:
    return [{"name": f"entity {i}", "label": "Entity"} for i in range(n)]


def _relations(n: int, rel_type: str = "RELATED_TO") -> list[dict[str, Any]]:
    return [
        {"source": f"entity {i}", "target": f"entity {i + 1}", "type": rel_type}
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_two_hundred_entities_do_not_cost_two_hundred_round_trips(monkeypatch):
    repo, statements, sessions = _repo(monkeypatch)

    counts = await repo.bulk_upsert(_entities(200), [])

    assert counts["nodes"] == 200
    assert len(statements) == 1, f"expected one UNWIND, got {len(statements)}"
    assert len(sessions) == 1, "a session was opened per entity"
    assert len(statements[0][1]["rows"]) == 200


@pytest.mark.asyncio
async def test_relations_are_grouped_by_relationship_type(monkeypatch):
    repo, statements, sessions = _repo(monkeypatch)

    relations = _relations(50, "WORKS_AT") + _relations(50, "FOUNDED")
    counts = await repo.bulk_upsert(_entities(10), relations)

    assert counts["edges"] == 100
    # One node statement plus one statement per distinct relationship type.
    assert len(statements) == 3
    assert len(sessions) == 1


@pytest.mark.asyncio
async def test_an_unsafe_relationship_type_is_still_normalised(monkeypatch):
    repo, statements, _ = _repo(monkeypatch)

    await repo.bulk_upsert(
        _entities(2),
        [{"source": "entity 0", "target": "entity 1", "type": "`) DELETE (n"}],
    )

    edge_statement = statements[-1][0]
    assert "DELETE" not in edge_statement
    assert "RELATED_TO" in edge_statement


@pytest.mark.asyncio
async def test_names_are_normalised_the_same_way_as_single_upserts(monkeypatch):
    repo, statements, _ = _repo(monkeypatch)

    await repo.bulk_upsert(
        [{"name": "  iran's   missile  arsenal ", "label": "Topic"}],
        [{"source": "  iran's   missile  arsenal ", "target": "x", "type": "MENTIONS"}],
    )

    assert statements[0][1]["rows"][0]["name"] == "Iran's Missile Arsenal"
    assert statements[1][1]["rows"][0]["src"] == "Iran's Missile Arsenal"


@pytest.mark.asyncio
async def test_nothing_to_write_makes_no_round_trip(monkeypatch):
    repo, statements, sessions = _repo(monkeypatch)

    assert await repo.bulk_upsert([], []) == {"nodes": 0, "edges": 0}
    assert statements == []
    assert sessions == []


@pytest.mark.asyncio
async def test_a_very_large_batch_is_chunked_rather_than_one_transaction(monkeypatch):
    repo, statements, _ = _repo(monkeypatch)

    await repo.bulk_upsert(_entities(2500), [])

    assert len(statements) > 1, "2500 nodes went out as a single transaction"
    assert sum(len(params["rows"]) for _, params in statements) == 2500
