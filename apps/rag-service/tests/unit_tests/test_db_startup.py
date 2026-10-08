from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path


def test_run_startup_migrations_ensures_database_before_alembic(monkeypatch):
    from src.shared.postgres import startup

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
        startup, "run_database_bootstrap", lambda: events.append("ensure")
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

    monkeypatch.setattr(startup, "_migration_lock", nullcontext)
    monkeypatch.setattr(
        startup, "_adopt_legacy_version_table", lambda: events.append("adopt")
    )
    startup.run_startup_migrations()

    assert events == [
        "retry:postgres:bootstrap_database",
        "ensure",
        "retry:postgres:adopt_legacy_version_table",
        "adopt",
        "retry:postgres:run_migrations",
        "upgrade:head",
    ]
    assert options["script_location"].replace("\\", "/").endswith(
        "apps/rag-service/src/shared/postgres/migrations"
    )
    assert options["prepend_sys_path"].replace("\\", "/").endswith("apps/rag-service")
    assert startup._build_alembic_config().attributes["configure_logger"] is False
    assert (
        "RAG service database migration check: current=%s target=%s",
        ("0002", "0003"),
    ) in logs
    assert (
        "RAG service database migrations completed: current=%s target=%s",
        ("0003", "0003"),
    ) in logs


def test_redis_connect_and_schema_bootstrap_are_wrapped_in_retry_async():
    server_py = (Path(__file__).parents[2] / "src/server.py").read_text()

    assert "retry_async" in server_py
    assert 'dependency="redis"' in server_py
    assert "AsyncRedisPool.connect" in server_py
    assert 'operation_name="connect"' in server_py
    assert 'dependency="postgres"' in server_py


async def test_lifespan_neo4j_failure_records_degraded_and_continues(monkeypatch):
    from src import server
    from src.graph import connection as neo4j_connection
    from src.shared.observability import dependency_registry

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

    async def fake_setup():
        return None

    async def fake_neo4j_driver():
        raise ConnectionError("neo4j refused")

    monkeypatch.setattr(server, "run_startup_migrations", lambda: None)
    monkeypatch.setattr(server, "retry_async", fake_retry_async)
    monkeypatch.setattr(server.AsyncRedisPool, "connect", fake_connect)
    monkeypatch.setattr(server.AsyncRedisPool, "close", fake_close)
    monkeypatch.setattr(server.CollectionsManager, "setup", fake_setup)
    monkeypatch.setattr(neo4j_connection, "get_neo4j_driver", fake_neo4j_driver)

    async with server.lifespan(server.APP):
        pass

    assert dependency_registry.get("neo4j").status == "degraded"
    assert dependency_registry.get("postgres").status == "ok"
    assert dependency_registry.get("redis").status == "ok"


def test_bootstrap_revision_creates_database_on_template1(monkeypatch):
    import runpy
    from contextlib import nullcontext
    from types import SimpleNamespace

    from alembic import op

    statements = []
    class Connection:
        def execute(self, statement, params=None):
            statements.append(str(statement))
            return SimpleNamespace(scalar=lambda: "template1", fetchone=lambda: None)

    monkeypatch.setattr(op, "get_bind", lambda: Connection())
    monkeypatch.setattr(op, "get_context", lambda: SimpleNamespace(autocommit_block=nullcontext))
    for key, value in {"USER": "test_role", "PASSWORD": "test_password", "DB": "test_database"}.items():
        monkeypatch.setenv(f"POSTGRES_RAG_SERVICE_{key}", value)
    revision = runpy.run_path(str(Path(__file__).resolve().parents[2] / "src/shared/postgres/migrations/versions/0000_bootstrap.py"))
    revision["upgrade"]()
    assert any('CREATE ROLE "test_role"' in statement for statement in statements)
    assert any('CREATE DATABASE "test_database"' in statement for statement in statements)


def test_alembic_environment_honors_bootstrap_overrides(monkeypatch):
    import runpy
    from contextlib import nullcontext
    from types import SimpleNamespace

    from alembic import context

    configured = []
    attributes = {"url_override": "postgresql+psycopg://admin:password@db/template1",
                  "version_table_override": "alembic_version_bootstrap_rag"}
    monkeypatch.setattr(context, "config", SimpleNamespace(attributes=attributes, config_file_name=None), raising=False)
    monkeypatch.setattr(context, "is_offline_mode", lambda: True)
    monkeypatch.setattr(context, "configure", lambda **kwargs: configured.append(kwargs))
    monkeypatch.setattr(context, "begin_transaction", nullcontext)
    monkeypatch.setattr(context, "run_migrations", lambda: None)
    module = runpy.run_path(str(Path(__file__).resolve().parents[2] / "src/shared/postgres/migrations/env.py"))
    assert configured[-1]["url"] == attributes["url_override"]
    assert configured[-1]["version_table"] == attributes["version_table_override"]
    module["do_run_migrations"](object())
    assert configured[-1]["version_table"] == attributes["version_table_override"]


class _FakeConnection:
    """A psycopg connection whose ``to_regclass`` answers come from ``tables``."""

    def __init__(self, tables: set[str]) -> None:
        self.tables = tables
        self.statements: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement: str):
        self.statements.append(statement)
        if statement.startswith("SELECT to_regclass"):
            name = statement.split("'")[1]
            found = name if name in self.tables else None
            return type("Result", (), {"fetchone": lambda self_: (found,)})()
        return None


def _adopt_with(monkeypatch, tables: set[str]) -> _FakeConnection:
    from src.shared.postgres import startup

    conn = _FakeConnection(tables)
    monkeypatch.setattr(startup, "_connect_to_service_database", lambda **_: conn)
    startup._adopt_legacy_version_table()
    return conn


def test_a_legacy_version_table_is_renamed_in_place(monkeypatch):
    conn = _adopt_with(monkeypatch, {"alembic_version_langconnect"})

    assert (
        "ALTER TABLE alembic_version_langconnect RENAME TO alembic_version_rag"
        in conn.statements
    )


def test_a_database_that_already_has_the_new_table_is_left_alone(monkeypatch):
    conn = _adopt_with(
        monkeypatch, {"alembic_version_langconnect", "alembic_version_rag"}
    )

    assert not any(s.startswith("ALTER") for s in conn.statements)


def test_a_fresh_database_has_nothing_to_adopt(monkeypatch):
    conn = _adopt_with(monkeypatch, set())

    assert not any(s.startswith("ALTER") for s in conn.statements)
