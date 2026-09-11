from __future__ import annotations

from pathlib import Path


def test_run_startup_migrations_ensures_database_before_alembic(monkeypatch):
    from langconnect.database.postgres import startup

    events: list[str] = []
    options: dict[str, str] = {}
    logs: list[tuple[str, tuple[object, ...]]] = []

    class FakeConfig:
        def __init__(self, path: str) -> None:
            self.path = path
            self.attributes = {}

        def set_main_option(self, key: str, value: str) -> None:
            options[key] = value

    monkeypatch.setattr(
        startup, "ensure_database_exists", lambda: events.append("ensure")
    )
    monkeypatch.setattr(startup, "Config", FakeConfig)
    monkeypatch.setattr(
        startup.command,
        "upgrade",
        lambda config, revision: events.append(f"upgrade:{revision}"),
    )
    monkeypatch.setattr(
        startup,
        "retry_sync",
        lambda operation, *, operation_name, dependency: (
            events.append(f"retry:{dependency}:{operation_name}"),
            operation(),
        )[1],
    )
    revision_states = iter([("0002", "0003"), ("0003", "0003")])
    monkeypatch.setattr(
        startup, "_migration_revision_state", lambda config: next(revision_states)
    )
    monkeypatch.setattr(
        startup.logger,
        "info",
        lambda message, *args: logs.append((message, args)),
    )

    startup.run_startup_migrations()

    assert events == [
        "retry:postgres:ensure_database",
        "ensure",
        "retry:postgres:run_migrations",
        "upgrade:head",
    ]
    assert options["script_location"].endswith(
        "apps/rag-service/langconnect/database/postgres/migrations"
    )
    assert options["prepend_sys_path"].endswith("apps/rag-service")
    assert startup._build_alembic_config().attributes["configure_logger"] is False
    assert (
        "LangConnect database migration check: current=%s target=%s",
        ("0002", "0003"),
    ) in logs
    assert (
        "LangConnect database migrations completed: current=%s target=%s",
        ("0003", "0003"),
    ) in logs


def test_redis_connect_and_schema_bootstrap_are_wrapped_in_retry_async():
    server_py = (Path(__file__).parents[2] / "langconnect/server.py").read_text()

    assert "retry_async" in server_py
    assert 'dependency="redis"' in server_py
    assert "AsyncRedisPool.connect" in server_py
    assert 'operation_name="connect"' in server_py
    assert 'operation_name="bootstrap_schema"' in server_py
    assert 'dependency="postgres"' in server_py
    assert "ensure_schema" in server_py


async def test_lifespan_neo4j_failure_records_degraded_and_continues(monkeypatch):
    from langconnect import server
    from langconnect.database.neo4j import connection as neo4j_connection
    from langconnect.observability import dependency_registry

    dependency_registry._states.clear()

    async def fake_retry_async(
        operation: object,
        *,
        operation_name: str,
        dependency: str,
        **kwargs: object,
    ) -> object:
        return await operation()  # type: ignore[no-any-return]

    async def fake_connect(config):
        return object()

    async def fake_close():
        return None

    async def fake_ensure_schema():
        return None

    async def fake_setup():
        return None

    async def fake_neo4j_driver():
        raise ConnectionError("neo4j refused")

    monkeypatch.setattr(server, "retry_async", fake_retry_async)
    monkeypatch.setattr(server.AsyncRedisPool, "connect", fake_connect)
    monkeypatch.setattr(server.AsyncRedisPool, "close", fake_close)
    monkeypatch.setattr(server, "ensure_schema", fake_ensure_schema)
    monkeypatch.setattr(server.CollectionsManager, "setup", fake_setup)
    monkeypatch.setattr(neo4j_connection, "get_neo4j_driver", fake_neo4j_driver)

    async with server.lifespan(server.APP):
        pass

    assert dependency_registry.get("neo4j").status == "degraded"
    assert dependency_registry.get("postgres").status == "ok"
    assert dependency_registry.get("redis").status == "ok"
