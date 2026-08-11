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
