from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_pool_creation_ensures_database_first(monkeypatch):
    from src.core.database import DatabaseManager

    events: list[str] = []

    class FakeSettings:
        @property
        def postgres_config(self):
            return {
                "user": "postgres",
                "password": "secret",
                "host": "localhost",
                "port": 8124,
                "database": "tools",
            }

    class FakePool:
        pass

    class FakeAsyncpg:
        async def create_pool(self, **kwargs):
            events.append(f"pool:{kwargs['database']}")
            return FakePool()

    manager = DatabaseManager()
    manager._pool = None
    monkeypatch.setattr("src.core.database.get_settings", lambda: FakeSettings())
    monkeypatch.setattr("src.core.database.asyncpg", FakeAsyncpg())
    monkeypatch.setattr(
        "src.core.database.ensure_database_exists",
        lambda: events.append("ensure"),
    )

    await manager.get_pool()

    assert events == ["ensure", "pool:tools"]


@pytest.mark.asyncio
async def test_pool_creation_wraps_startup_connections_with_retry(monkeypatch):
    from src.core.database import DatabaseManager

    events: list[str] = []

    class FakeSettings:
        @property
        def postgres_config(self):
            return {
                "user": "postgres",
                "password": "secret",
                "host": "localhost",
                "port": 8124,
                "database": "tools",
            }

    class FakePool:
        pass

    class FakeAsyncpg:
        async def create_pool(self, **kwargs):
            events.append(f"pool:{kwargs['database']}")
            return FakePool()

    async def fake_retry_async(operation, *, operation_name, dependency, **kwargs):
        events.append(f"retry:{dependency}:{operation_name}")
        result = operation()
        if hasattr(result, "__await__"):
            return await result
        return result

    manager = DatabaseManager()
    manager._pool = None
    monkeypatch.setattr("src.core.database.get_settings", lambda: FakeSettings())
    monkeypatch.setattr("src.core.database.asyncpg", FakeAsyncpg())
    monkeypatch.setattr(
        "src.core.database.ensure_database_exists",
        lambda: events.append("ensure"),
    )
    monkeypatch.setattr("src.core.database.retry_async", fake_retry_async)

    await manager.get_pool()

    assert events == [
        "retry:postgres:ensure_database",
        "ensure",
        "retry:postgres:create_pool",
        "pool:tools",
    ]
