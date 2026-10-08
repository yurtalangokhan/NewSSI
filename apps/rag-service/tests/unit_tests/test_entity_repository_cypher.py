"""execute_cypher must default to a read-only session with a server-side
timeout, so an admin query cannot write and cannot hold a connection open
indefinitely. Spec T1.

Access control on this endpoint (admin check + collection ownership) was
already tightened before this task; what remained was that an admin query
could still write, had no timeout, and the raw Neo4j exception was
returned to the caller.
"""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import neo4j
import pytest

from src.graph.repositories.entity_repository import EntityRepository


class _FakeResult:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        return self._iter()

    async def _iter(self) -> AsyncGenerator[dict[str, Any], None]:
        for record in self._records:
            yield record


class _FakeSession:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.run = AsyncMock(return_value=_FakeResult(records))


class _FakeDriver:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records
        self.captured_access_mode: object = None

    def session(self, **kwargs: object) -> AbstractAsyncContextManager[_FakeSession]:
        self.captured_access_mode = kwargs.get("default_access_mode")
        session = _FakeSession(self._records)
        self._last_session = session

        @asynccontextmanager
        async def _cm() -> AsyncIterator[_FakeSession]:
            yield session

        return _cm()


@pytest.fixture
def repo(monkeypatch):
    driver = _FakeDriver(records=[{"n": {"name": "Alice"}}])
    repository = EntityRepository("col-1")
    monkeypatch.setattr(repository, "_driver", AsyncMock(return_value=driver))
    return repository, driver


@pytest.mark.asyncio
async def test_execute_cypher_defaults_to_read_only(repo):
    repository, driver = repo
    await repository.execute_cypher("MATCH (n) RETURN n", {})
    assert driver.captured_access_mode == neo4j.READ_ACCESS


@pytest.mark.asyncio
async def test_execute_cypher_honours_explicit_write_mode(repo):
    repository, driver = repo
    await repository.execute_cypher("CREATE (n:X)", {}, read_only=False)
    assert driver.captured_access_mode == neo4j.WRITE_ACCESS


@pytest.mark.asyncio
async def test_execute_cypher_applies_a_server_side_timeout(repo):
    repository, driver = repo
    await repository.execute_cypher("MATCH (n) RETURN n", {}, timeout_s=5.0)
    session = driver._last_session
    call_args = session.run.call_args
    query_arg = call_args.args[0]
    assert isinstance(query_arg, neo4j.Query)
    assert query_arg.timeout == 5.0


@pytest.mark.asyncio
async def test_execute_cypher_returns_records_as_dicts(repo):
    repository, _ = repo
    results = await repository.execute_cypher("MATCH (n) RETURN n", {})
    assert results == [{"n": {"name": "Alice"}}]
