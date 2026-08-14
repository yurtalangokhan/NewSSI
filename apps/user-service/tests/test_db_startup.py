from __future__ import annotations

import importlib.util
from pathlib import Path


def test_alembic_metadata_does_not_register_deprecated_coarse_roles_table():
    from src.core.database.models import Base

    assert "coarse_roles" not in Base.metadata.tables


def test_run_startup_migrations_ensures_database_before_alembic(monkeypatch):
    from src.core.database import startup

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
    revision_states = iter([("0019", "0021"), ("0021", "0021")])
    monkeypatch.setattr(startup, "_migration_revision_state", lambda config: next(revision_states))
    monkeypatch.setattr(
        startup.logger,
        "info",
        lambda message, *args: logs.append((message, args)),
    )

    startup.run_startup_migrations()

    assert events == ["ensure", "upgrade:head"]
    assert options["script_location"].endswith("apps/user-service/src/core/database/migrations")
    assert options["prepend_sys_path"].endswith("apps/user-service/src")
    assert startup._build_alembic_config().attributes["configure_logger"] is False
    assert (
        "User service database migration check: current=%s target=%s",
        ("0019", "0021"),
    ) in logs
    assert (
        "User service database migrations completed: current=%s target=%s",
        ("0021", "0021"),
    ) in logs


def test_organization_repair_migration_recreates_missing_tables_idempotently():
    migration_path = (
        Path(__file__).parents[1]
        / "src"
        / "core"
        / "database"
        / "migrations"
        / "versions"
        / "0032_repair_missing_organization_tables.py"
    )
    spec = importlib.util.spec_from_file_location("organization_repair_migration", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    executed: list[str] = []

    class Operations:
        @staticmethod
        def execute(statement: str) -> None:
            executed.append(statement)

    migration.op = Operations

    migration.upgrade()

    ddl = "\n".join(executed)
    assert "CREATE TABLE IF NOT EXISTS organizations" in ddl
    assert "CREATE TABLE IF NOT EXISTS user_organizations" in ddl
    assert "CREATE TABLE IF NOT EXISTS resource_permissions" in ddl
    assert "CREATE TABLE IF NOT EXISTS permission_audit_logs" in ddl
    assert "CREATE TABLE IF NOT EXISTS organization_layouts" in ddl


def test_organization_code_index_repair_migration_matches_model_contract():
    migration_path = (
        Path(__file__).parents[1]
        / "src"
        / "core"
        / "database"
        / "migrations"
        / "versions"
        / "0033_repair_organization_code_unique_index.py"
    )
    spec = importlib.util.spec_from_file_location(
        "organization_code_index_repair_migration", migration_path
    )
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    executed: list[str] = []

    class Operations:
        @staticmethod
        def execute(statement: str) -> None:
            executed.append(statement)

    migration.op = Operations

    migration.upgrade()

    ddl = "\n".join(executed)
    assert migration.revision == "0033"
    assert migration.down_revision == "0032"
    assert "ALTER TABLE organizations DROP CONSTRAINT IF EXISTS organizations_code_key" in ddl
    assert "DROP INDEX IF EXISTS ix_organizations_code" in ddl
    assert "CREATE UNIQUE INDEX IF NOT EXISTS ix_organizations_code" in ddl
