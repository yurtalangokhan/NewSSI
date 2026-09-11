from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path


def test_alembic_revision_graph_has_unique_revisions_and_single_head():
    versions_dir = Path(__file__).parents[1] / "src/core/db/migrations/versions"
    revisions: dict[str, str | tuple[str, ...] | None] = {}
    revision_sources: list[tuple[str, str]] = []

    for migration_path in sorted(versions_dir.glob("*.py")):
        spec = importlib.util.spec_from_file_location(migration_path.stem, migration_path)
        assert spec and spec.loader
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        revision = migration.revision
        revisions[revision] = migration.down_revision
        revision_sources.append((revision, migration_path.name))

    duplicates = {
        revision: [source for candidate, source in revision_sources if candidate == revision]
        for revision, count in Counter(revision for revision, _ in revision_sources).items()
        if count > 1
    }
    assert duplicates == {}

    referenced_revisions: set[str] = set()
    for down_revision in revisions.values():
        if isinstance(down_revision, tuple):
            referenced_revisions.update(down_revision)
        elif down_revision is not None:
            referenced_revisions.add(down_revision)

    heads = sorted(set(revisions) - referenced_revisions)
    assert heads == ["0045"]


def test_sub_agent_ids_migration_uses_jsonb_for_gin_index():
    migration = (
        Path(__file__).parents[1] / "src/core/db/migrations/versions/0025_add_sub_agent_ids.py"
    )

    assert "postgresql.JSONB()" in migration.read_text()


def test_agents_migration_uses_existing_uuid_function_without_extension_ddl():
    migration = (
        Path(__file__).parents[1] / "src/core/db/migrations/versions/0036_merge_agent_tables.py"
    ).read_text()

    assert "gen_random_uuid()" in migration
    assert "CREATE EXTENSION" not in migration


def test_agents_migration_casts_legacy_json_columns_to_jsonb():
    migration = (
        Path(__file__).parents[1] / "src/core/db/migrations/versions/0036_merge_agent_tables.py"
    ).read_text()

    for column in (
        "rag_config",
        "mcp_tools",
        "mcp_tool_configs",
        "sub_agents",
        "stages",
        "tags",
    ):
        assert f"COALESCE({column}::jsonb," in migration


def test_agent_definition_rows_do_not_reuse_unique_persona_identity():
    migration = (
        Path(__file__).parents[1] / "src/core/db/migrations/versions/0036_merge_agent_tables.py"
    ).read_text()

    assert "legacy_definition_id, legacy_persona_id, name" not in migration
    assert "id, persona_id, name, description, agent_type" not in migration


def test_alembic_metadata_registers_all_service_owned_tables():
    from core.db.models import Base, register_external_models

    register_external_models()

    assert {
        "agent_definitions",
        "providers",
        "user_provider_configs",
    }.issubset(Base.metadata.tables)


def test_alembic_autogenerate_ignores_langgraph_runtime_tables():
    env_py = (Path(__file__).parents[1] / "src/core/db/migrations/env.py").read_text()

    assert "LANGGRAPH_RUNTIME_TABLES" in env_py
    assert "checkpoints" in env_py
    assert "checkpoint_writes" in env_py
    assert "checkpoint_blobs" in env_py
    assert "store" in env_py
    assert "return False" in env_py


def test_run_startup_migrations_ensures_database_before_alembic(monkeypatch):
    from core.db import startup

    events: list[str] = []
    options: dict[str, str] = {}
    logs: list[tuple[str, tuple[object, ...]]] = []

    class FakeConfig:
        def __init__(self, path: str) -> None:
            self.path = path
            self.attributes = {}

        def set_main_option(self, key: str, value: str) -> None:
            options[key] = value

    monkeypatch.setattr(startup, "ensure_database_exists", lambda: events.append("ensure"))
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
    revision_states = iter([("0027", "0028"), ("0028", "0028")])
    monkeypatch.setattr(startup, "_migration_revision_state", lambda config: next(revision_states))
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
    assert options["script_location"].endswith("apps/agent-service/src/core/db/migrations")
    assert options["prepend_sys_path"].endswith("apps/agent-service/src")
    assert startup._build_alembic_config().attributes["configure_logger"] is False
    assert (
        "Agent service database migration check: current=%s target=%s",
        ("0027", "0028"),
    ) in logs
    assert (
        "Agent service database migrations completed: current=%s target=%s",
        ("0028", "0028"),
    ) in logs


def test_ensure_database_exists_creates_missing_database(monkeypatch):
    from core.db import startup

    statements: list[object] = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def execute(self, statement, params=None):
            statements.append((statement, params))
            if params == ("agent_service",):
                return self
            return None

        def fetchone(self):
            return None

    def fake_connect(**kwargs):
        statements.append(kwargs)
        return FakeConnection()

    monkeypatch.setattr(startup.settings, "POSTGRES_HOST", "localhost")
    monkeypatch.setattr(startup.settings, "POSTGRES_PORT", 8124)
    monkeypatch.setattr(startup.settings, "POSTGRES_USER", "postgres")
    monkeypatch.setattr(startup.settings, "POSTGRES_PASSWORD", "secret")
    monkeypatch.setattr(startup.settings, "POSTGRES_DB", "agent_service")
    monkeypatch.setattr(startup.psycopg, "connect", fake_connect)

    startup.ensure_database_exists()

    assert statements[0]["dbname"] == "postgres"
    sql_statements = [statement for statement in statements if isinstance(statement, tuple)]
    assert any("CREATE DATABASE" in str(statement[0]) for statement in sql_statements)


def test_redis_connect_is_wrapped_in_retry_async():
    app_py = (Path(__file__).parents[1] / "src/app.py").read_text()

    assert "retry_async" in app_py
    assert 'dependency="redis"' in app_py
    assert "AsyncRedisPool.connect" in app_py
    assert 'operation_name="connect"' in app_py


def test_tools_service_init_is_degraded_not_fatal():
    app_py = (Path(__file__).parents[1] / "src/app.py").read_text()

    assert "initialize_builtin" in app_py
    assert 'record_degraded(\n                        "tools-service"' in app_py
    assert "startup.dependency.degraded" in app_py
    assert "tools-service is unavailable; tool execution will be degraded." in app_py
