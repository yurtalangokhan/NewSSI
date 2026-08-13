from __future__ import annotations

from pathlib import Path


def test_sub_agent_ids_migration_uses_jsonb_for_gin_index():
    migration = (
        Path(__file__).parents[1]
        / "src/core/db/migrations/versions/0025_add_sub_agent_ids.py"
    )

    assert "postgresql.JSONB()" in migration.read_text()


def test_alembic_metadata_registers_all_service_owned_tables():
    from core.db.models import Base, register_external_models

    register_external_models()

    assert {
        "agent_definitions",
        "providers",
        "user_provider_configs",
        "user_memory",
    }.issubset(Base.metadata.tables)


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
    revision_states = iter([("0027", "0028"), ("0028", "0028")])
    monkeypatch.setattr(startup, "_migration_revision_state", lambda config: next(revision_states))
    monkeypatch.setattr(
        startup.logger,
        "info",
        lambda message, *args: logs.append((message, args)),
    )

    startup.run_startup_migrations()

    assert events == ["ensure", "upgrade:head"]
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
