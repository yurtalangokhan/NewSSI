from __future__ import annotations

from collections import Counter
from contextlib import nullcontext
import importlib.util
from pathlib import Path
import re

from config_manager import env


def test_alembic_revision_graph_has_unique_revisions_and_single_head():
    versions_dir = Path(__file__).parents[3] / "src/infrastructure/db/migrations/versions"
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
    assert heads == ["0052"]


def test_sub_agent_ids_migration_uses_jsonb_for_gin_index():
    migration = (
        Path(__file__).parents[3]
        / "src/infrastructure/db/migrations/versions/0025_add_sub_agent_ids.py"
    )

    assert "postgresql.JSONB()" in migration.read_text()


def test_agents_migration_uses_existing_uuid_function_without_extension_ddl():
    migration = (
        Path(__file__).parents[3]
        / "src/infrastructure/db/migrations/versions/0036_merge_agent_tables.py"
    ).read_text()

    assert "gen_random_uuid()" in migration
    assert "CREATE EXTENSION" not in migration


def test_agents_migration_casts_legacy_json_columns_to_jsonb():
    migration = (
        Path(__file__).parents[3]
        / "src/infrastructure/db/migrations/versions/0036_merge_agent_tables.py"
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
        Path(__file__).parents[3]
        / "src/infrastructure/db/migrations/versions/0036_merge_agent_tables.py"
    ).read_text()

    assert "legacy_definition_id, legacy_persona_id, name" not in migration
    assert "id, persona_id, name, description, agent_type" not in migration


def test_alembic_metadata_registers_all_service_owned_tables():
    from infrastructure.db.models import Base, register_external_models

    register_external_models()

    assert {
        "agent_definitions",
        "providers",
        "user_provider_configs",
    }.issubset(Base.metadata.tables)


def test_alembic_autogenerate_ignores_langgraph_runtime_tables():
    env_py = (Path(__file__).parents[3] / "src/infrastructure/db/migrations/env.py").read_text()

    assert "LANGGRAPH_RUNTIME_TABLES" in env_py
    assert "checkpoints" in env_py
    assert "checkpoint_writes" in env_py
    assert "checkpoint_blobs" in env_py
    assert "store" in env_py
    assert "include_object" in env_py


def test_run_startup_migrations_ensures_database_before_alembic(monkeypatch):
    from infrastructure.db import startup

    events: list[str] = []
    options: dict[str, str] = {}
    logs: list[tuple[str, tuple[object, ...]]] = []

    class FakeConfig:
        def __init__(self, path: str) -> None:
            self.path = path
            self.attributes = {}

        def set_main_option(self, key: str, value: str) -> None:
            options[key] = value

    monkeypatch.setattr(startup, "run_database_bootstrap", lambda: events.append("bootstrap"))
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

    monkeypatch.setattr(startup, "_migration_lock", nullcontext)
    startup.run_startup_migrations()

    assert events == [
        "retry:postgres:bootstrap_database",
        "bootstrap",
        "retry:postgres:run_migrations",
        "upgrade:head",
    ]
    assert options["script_location"].replace("\\", "/").endswith(
        "apps/agent-service/src/infrastructure/db/migrations"
    )
    assert options["prepend_sys_path"].replace("\\", "/").endswith("apps/agent-service/src")
    assert startup._build_alembic_config().attributes["configure_logger"] is False
    assert (
        "Agent service database migration check: current=%s target=%s",
        ("0027", "0028"),
    ) in logs
    assert (
        "Agent service database migrations completed: current=%s target=%s",
        ("0028", "0028"),
    ) in logs


def test_bootstrap_runs_against_the_admin_maintenance_database(monkeypatch):
    """The service role and database are created by the 0000_bootstrap revision.

    It cannot run against the service database (which may not exist yet), so it
    goes through the admin role against the always-present ``postgres``
    maintenance database, under its own version table so the main chain stays
    linear.
    """
    from infrastructure.db import startup

    upgrades: list[tuple[object, str]] = []
    cfg = startup._build_alembic_config()
    monkeypatch.setattr(startup, "_build_alembic_config", lambda: cfg)
    monkeypatch.setattr(startup.command, "upgrade", lambda config, revision: upgrades.append((config, revision)))

    startup.run_database_bootstrap()

    assert [revision for _, revision in upgrades] == ["0000_bootstrap"]
    assert cfg.attributes["version_table_override"] == "alembic_version_bootstrap_agent"
    url = cfg.attributes["url_override"]
    assert url.endswith("/template1")
    assert env.POSTGRES_ADMIN_USER in url


def test_redis_connect_is_wrapped_in_retry_async():
    app_py = (Path(__file__).parents[3] / "src/app.py").read_text()

    assert "retry_async" in app_py
    assert 'dependency="redis"' in app_py
    assert "AsyncRedisPool.connect" in app_py
    assert 'operation_name="connect"' in app_py


def test_tools_service_init_is_degraded_not_fatal():
    app_py = (Path(__file__).parents[3] / "src/app.py").read_text()

    assert "initialize_builtin" in app_py
    # Girintiye dayanikli: kaynak yeniden duzenlendiginde (orn. with birlestirme)
    # bu testin niyeti — degraded kaydin varligi — korunmali.
    assert re.search(r'record_degraded\(\s*"tools-service"', app_py)
    assert "startup.dependency.degraded" in app_py
    assert "tools-service is unavailable; tool execution will be degraded." in app_py


def test_bootstrap_revision_creates_database_on_template1(monkeypatch):
    from contextlib import nullcontext
    import runpy
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
        monkeypatch.setenv(f"POSTGRES_AGENT_SERVICE_{key}", value)
    revision = runpy.run_path(str(Path(__file__).resolve().parents[3] / "src/infrastructure/db/migrations/versions/0000_bootstrap.py"))
    revision["upgrade"]()
    assert any('CREATE ROLE "test_role"' in statement for statement in statements)
    assert any('CREATE DATABASE "test_database"' in statement for statement in statements)


def test_alembic_environment_honors_bootstrap_overrides(monkeypatch):
    from contextlib import nullcontext
    import runpy
    from types import SimpleNamespace

    from alembic import context

    configured = []
    attributes = {"url_override": "postgresql+psycopg://admin:password@db/template1",
                  "version_table_override": "alembic_version_bootstrap_agent"}
    monkeypatch.setattr(context, "config", SimpleNamespace(attributes=attributes, config_file_name=None), raising=False)
    monkeypatch.setattr(context, "is_offline_mode", lambda: True)
    monkeypatch.setattr(context, "configure", lambda **kwargs: configured.append(kwargs))
    monkeypatch.setattr(context, "begin_transaction", nullcontext)
    monkeypatch.setattr(context, "run_migrations", lambda: None)
    module = runpy.run_path(str(Path(__file__).resolve().parents[3] / "src/infrastructure/db/migrations/env.py"))
    assert configured[-1]["url"] == attributes["url_override"]
    assert configured[-1]["version_table"] == attributes["version_table_override"]
    module["do_run_migrations"](object())
    assert configured[-1]["version_table"] == attributes["version_table_override"]
