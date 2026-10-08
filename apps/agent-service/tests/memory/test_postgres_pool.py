"""Spec: the shared psycopg connection pool backing the checkpointer and
store must be a well-behaved resource -- closeable on shutdown, honestly
labeled for DB-side observability, and explicit about its own timeouts.

Before this:
  - Nothing ever closed `_shared_pool`; every other startup resource (Redis,
    the SQLAlchemy engine, background workers) was explicitly closed in
    app.py's lifespan shutdown, but this pool was not.
  - `application_suffix` only took effect on the whole pool's first caller
    (get_postgres_saver or get_postgres_store, whichever ran first), so
    `pg_stat_activity.application_name` could show "agent-service-saver"
    for connections actually used by the store, and vice versa.
  - `timeout`/`reconnect_timeout` were never passed, relying on whatever
    psycopg_pool's library defaults happen to be.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import memory.postgres as pg


class _FakePool:
    """Stands in for psycopg_pool.AsyncConnectionPool."""

    check_connection = staticmethod(lambda conn: None)

    def __init__(self, conninfo, **kwargs):
        self.conninfo = conninfo
        self.kwargs = kwargs
        self.closed = False
        self.open = AsyncMock(side_effect=self._mark_open)
        self.close = AsyncMock(side_effect=self._mark_closed)

    async def _mark_open(self):
        self.closed = False

    async def _mark_closed(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_shared_pool(monkeypatch):
    """Every test starts from a clean module-global pool state."""
    monkeypatch.setattr(pg, "_shared_pool", None)
    monkeypatch.setattr(pg, "AsyncConnectionPool", _FakePool)
    monkeypatch.setattr(
        pg,
        "validate_postgres_config",
        lambda: None,
    )
    monkeypatch.setattr(pg, "get_postgres_conninfo", lambda: "postgresql://fake")
    yield


@pytest.mark.asyncio
async def test_close_shared_pool_closes_the_open_pool():
    pool = await pg.get_or_create_shared_pool()
    assert pool.closed is False

    await pg.close_shared_pool()

    assert pool.closed is True


@pytest.mark.asyncio
async def test_close_shared_pool_is_a_noop_when_no_pool_was_ever_created():
    # Must not raise -- shutdown always calls this even if the app crashed
    # before persistence was ever initialized.
    await pg.close_shared_pool()


@pytest.mark.asyncio
async def test_close_shared_pool_lets_a_new_pool_be_created_afterwards():
    first = await pg.get_or_create_shared_pool()
    await pg.close_shared_pool()

    second = await pg.get_or_create_shared_pool()

    assert second is not first
    assert second.closed is False


@pytest.mark.asyncio
async def test_get_or_create_shared_pool_no_longer_takes_a_per_caller_suffix():
    import inspect

    sig = inspect.signature(pg.get_or_create_shared_pool)
    assert "application_suffix" not in sig.parameters


@pytest.mark.asyncio
async def test_pool_application_name_is_the_same_regardless_of_which_caller_creates_it_first():
    pool = await pg.get_or_create_shared_pool()
    assert pool.kwargs["kwargs"]["application_name"] == pg.env.POSTGRES_APPLICATION_NAME


@pytest.mark.asyncio
async def test_pool_is_created_with_explicit_timeout_settings(monkeypatch):
    monkeypatch.setenv("POSTGRES_POOL_TIMEOUT_SECONDS", "12.0")
    monkeypatch.setenv("POSTGRES_POOL_RECONNECT_TIMEOUT_SECONDS", "34.0")

    pool = await pg.get_or_create_shared_pool()

    assert pool.kwargs["timeout"] == 12.0
    assert pool.kwargs["reconnect_timeout"] == 34.0


@pytest.mark.asyncio
async def test_store_setup_tolerates_duplicate_column_like_the_saver_does(monkeypatch):
    from psycopg import errors as pg_errors

    fake_store = MagicMock()
    fake_store.setup = AsyncMock(side_effect=pg_errors.DuplicateColumn("already there"))
    monkeypatch.setattr(pg, "AsyncPostgresStore", MagicMock(return_value=fake_store))

    # Must not raise -- a legacy DB with partially-applied migrations should
    # start up the same way the checkpointer already tolerates.
    async with pg.get_postgres_store() as store:
        assert store is fake_store
