from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path


def test_alembic_revision_graph_has_unique_revisions_and_single_head():
    versions_dir = Path(__file__).parents[1] / "src/core/database/migrations/versions"
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
    assert heads == ["0044"]


def test_alembic_metadata_does_not_register_deprecated_coarse_roles_table():
    from src.core.database.models import Base

    assert "coarse_roles" not in Base.metadata.tables


def test_role_normalization_preserves_role_table_boundaries():
    migration = (
        Path(__file__).parents[1] / "src/core/database/migrations/versions/0040_normalize_roles.py"
    ).read_text()

    assert "role_name VARCHAR(100) NOT NULL," in migration
    assert "parent_role VARCHAR(100) NOT NULL REFERENCES composite_roles(name)" in migration
    assert "child_role VARCHAR(100) NOT NULL REFERENCES roles(name)" in migration
    assert "FOREIGN KEY (role_name) REFERENCES roles(name)" not in migration


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
    monkeypatch.setattr(
        startup,
        "retry_sync",
        lambda operation, *, operation_name, dependency: (
            events.append(f"retry:{dependency}:{operation_name}"),
            operation(),
        )[1],
    )
    revision_states = iter([("0019", "0021"), ("0021", "0021")])
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


def test_enterprise_admin_organization_permissions_are_restored():
    migration_path = (
        Path(__file__).parents[1]
        / "src"
        / "core"
        / "database"
        / "migrations"
        / "versions"
        / "0035_restore_enterprise_admin_organization_permissions.py"
    )
    spec = importlib.util.spec_from_file_location(
        "enterprise_admin_organization_permissions_migration", migration_path
    )
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    statements: list[str] = []

    class Operations:
        @staticmethod
        def execute(statement: object) -> None:
            statements.append(str(statement))

    migration.op = Operations
    migration.upgrade()

    sql = " ".join(statements)
    assert migration.revision == "0035"
    assert migration.down_revision == "0034"
    assert "access-manager" in sql
    assert "org:list" in sql
    assert "org:read" in sql


def test_organization_write_permissions_migration_supports_normalized_role_permissions(
    monkeypatch,
):
    migration_path = (
        Path(__file__).parents[1]
        / "src"
        / "core"
        / "database"
        / "migrations"
        / "versions"
        / "0036_seed_organization_write_permissions.py"
    )
    spec = importlib.util.spec_from_file_location(
        "organization_write_permissions_migration", migration_path
    )
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    statements: list[str] = []

    class Operations:
        @staticmethod
        def get_bind() -> object:
            return object()

        @staticmethod
        def execute(statement: object) -> None:
            statements.append(str(statement))

    class Inspector:
        @staticmethod
        def has_table(table_name: str) -> bool:
            return table_name == "role_permissions"

        @staticmethod
        def get_columns(table_name: str) -> list[dict[str, str]]:
            assert table_name in {"roles", "composite_roles"}
            return [{"name": "name"}]

    migration.op = Operations
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: Inspector())
    migration.upgrade()

    sql = " ".join(statements)
    assert "INSERT INTO role_permissions" in sql
    assert "UPDATE roles" not in sql
    assert "UPDATE composite_roles" not in sql


def test_settings_permissions_migration_supports_normalized_role_permissions(
    monkeypatch,
):
    migration_path = (
        Path(__file__).parents[1]
        / "src"
        / "core"
        / "database"
        / "migrations"
        / "versions"
        / "0037_grant_settings_permissions_to_enterprise_admin.py"
    )
    spec = importlib.util.spec_from_file_location("settings_permissions_migration", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    statements: list[str] = []

    class Operations:
        @staticmethod
        def get_bind() -> object:
            return object()

        @staticmethod
        def execute(statement: object) -> None:
            statements.append(str(statement))

    class Inspector:
        @staticmethod
        def has_table(table_name: str) -> bool:
            return table_name == "role_permissions"

        @staticmethod
        def get_columns(table_name: str) -> list[dict[str, str]]:
            assert table_name in {"roles", "composite_roles"}
            return [{"name": "name"}]

    migration.op = Operations
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: Inspector())
    migration.upgrade()

    sql = " ".join(statements)
    assert "INSERT INTO role_permissions" in sql
    assert "UPDATE roles" not in sql
    assert "UPDATE composite_roles" not in sql


def test_drop_composite_role_is_admin_migration_skips_missing_table(monkeypatch):
    migration_path = (
        Path(__file__).parents[1]
        / "src"
        / "core"
        / "database"
        / "migrations"
        / "versions"
        / "0038_drop_composite_role_is_admin_column.py"
    )
    spec = importlib.util.spec_from_file_location(
        "drop_composite_role_is_admin_migration", migration_path
    )
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    calls: list[tuple[str, str]] = []

    class Operations:
        @staticmethod
        def get_bind() -> object:
            return object()

        @staticmethod
        def drop_column(table_name: str, column_name: str) -> None:
            calls.append((table_name, column_name))

    class Inspector:
        @staticmethod
        def has_table(table_name: str) -> bool:
            return False

    migration.op = Operations
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: Inspector())
    migration.upgrade()

    assert calls == []


def test_role_normalization_skips_legacy_jsonb_backfill_when_columns_are_missing(
    monkeypatch,
):
    migration_path = (
        Path(__file__).parents[1]
        / "src"
        / "core"
        / "database"
        / "migrations"
        / "versions"
        / "0040_normalize_roles.py"
    )
    spec = importlib.util.spec_from_file_location("role_normalization_migration", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    statements: list[str] = []

    class Operations:
        @staticmethod
        def get_bind() -> object:
            return object()

        @staticmethod
        def execute(statement: object) -> None:
            statements.append(str(statement))

    class Inspector:
        @staticmethod
        def has_table(table_name: str) -> bool:
            return table_name in {"roles", "role_permissions", "role_hierarchy"}

        @staticmethod
        def get_columns(table_name: str) -> list[dict[str, str]]:
            assert table_name in {"roles", "composite_roles"}
            return [{"name": "name"}]

    migration.op = Operations
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: Inspector())
    migration.upgrade()

    sql = " ".join(statements)
    assert "CREATE TABLE IF NOT EXISTS role_permissions" in sql
    assert "CREATE TABLE IF NOT EXISTS role_hierarchy" in sql
    assert "jsonb_array_elements_text(roles.permissions)" not in sql
    assert "jsonb_array_elements_text(composite_roles.permissions)" not in sql


def test_role_identity_repair_backfills_legacy_composite_roles(monkeypatch):
    migration_path = (
        Path(__file__).parents[1]
        / "src"
        / "core"
        / "database"
        / "migrations"
        / "versions"
        / "0041_repair_normalized_role_identities.py"
    )
    spec = importlib.util.spec_from_file_location("role_identity_repair_migration", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    statements: list[str] = []

    class Operations:
        @staticmethod
        def get_bind() -> object:
            return object()

        @staticmethod
        def execute(statement: object) -> None:
            statements.append(str(statement))

    class Inspector:
        @staticmethod
        def has_table(table_name: str) -> bool:
            return table_name in {
                "composite_roles",
                "roles",
                "role_permissions",
                "role_hierarchy",
            }

        @staticmethod
        def get_columns(table_name: str) -> list[dict[str, str]]:
            if table_name == "roles":
                return [
                    {"name": "name"},
                    {"name": "description"},
                    {"name": "service_client"},
                    {"name": "permissions"},
                    {"name": "created_at"},
                ]
            return [
                {"name": "name"},
                {"name": "permissions"},
                {"name": "role_ids"},
            ]

    migration.op = Operations
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: Inspector())
    migration.upgrade()

    sql = " ".join(statements)
    assert migration.down_revision == "0040"
    assert "INSERT INTO roles" in sql
    assert "FROM composite_roles" in sql
    assert "INSERT INTO role_permissions" in sql
    assert "INSERT INTO role_hierarchy" in sql
    assert "ON CONFLICT" in sql


def test_redis_connect_is_wrapped_in_retry_async():
    main_py = (Path(__file__).parents[1] / "src/main.py").read_text()

    assert "retry_async" in main_py
    assert 'dependency="redis"' in main_py
    assert "AsyncRedisPool.connect" in main_py
    assert 'operation_name="connect"' in main_py


def test_keycloak_admin_bootstrap_and_external_idp_sync_are_degraded():
    main_py = (Path(__file__).parents[1] / "src/main.py").read_text()

    # Admin bootstrap failure is degraded (record + continue).
    assert "keycloak is unavailable during default admin bootstrap; " in main_py
    assert "continuing without admin user sync." in main_py
    assert 'record_degraded(\n                    "keycloak"' in main_py
    assert "startup.dependency.degraded" in main_py

    # External IdP sync denial is degraded (record + continue).
    assert 'record_degraded(\n                            "keycloak_idp"' in main_py
    assert "Skipping external Keycloak identity provider sync" in main_py
