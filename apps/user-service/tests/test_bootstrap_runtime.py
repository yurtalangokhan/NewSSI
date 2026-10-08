"""Bootstrap must execute on maintenance databases with isolated version state."""

import importlib
import runpy
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from sqlalchemy.engine import make_url


@pytest.mark.parametrize("database", ["postgres", "template1"])
def test_bootstrap_revision_creates_role_and_database_on_maintenance_database(monkeypatch, database):
    migration = importlib.import_module("src.core.database.migrations.versions.0000_bootstrap")
    statements = []

    class Connection:
        def execute(self, statement, parameters=None):
            statements.append(str(statement))
            return SimpleNamespace(scalar=lambda: database, fetchone=lambda: None)

    monkeypatch.setattr(migration.op, "get_bind", lambda: Connection())
    monkeypatch.setattr(migration.op, "get_context", lambda: SimpleNamespace(autocommit_block=nullcontext))
    monkeypatch.setenv("POSTGRES_USER_SERVICE_USER", "test_user")
    monkeypatch.setenv("POSTGRES_USER_SERVICE_PASSWORD", "test_password")
    monkeypatch.setenv("POSTGRES_USER_SERVICE_DB", "test_database")

    migration.upgrade()

    assert statements[0] == "SELECT current_database()"
    assert any(statement.startswith("CREATE ROLE") for statement in statements)
    assert any(statement.startswith("CREATE DATABASE") for statement in statements)


def test_bootstrap_revision_skips_the_service_database(monkeypatch):
    migration = importlib.import_module("src.core.database.migrations.versions.0000_bootstrap")
    connection = SimpleNamespace(execute=lambda statement: SimpleNamespace(scalar=lambda: "user_database"))
    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    monkeypatch.setattr(migration, "_env", lambda name: pytest.fail("Service database must skip bootstrap"))
    migration.upgrade()


def test_startup_bootstrap_uses_user_specific_version_table(monkeypatch):
    from src.core.database import startup

    config = SimpleNamespace(attributes={})
    monkeypatch.setattr(startup, "_build_alembic_config", lambda: config)
    monkeypatch.setattr(startup, "env", SimpleNamespace(
        POSTGRES_ADMIN_USER="test_admin", POSTGRES_ADMIN_PASSWORD=SecretStr("test_password"),
        POSTGRES_HOST="test_host", POSTGRES_PORT=6543,
    ))
    calls = []
    monkeypatch.setattr(startup.command, "upgrade", lambda cfg, revision: calls.append((cfg, revision)))

    startup.run_database_bootstrap()

    assert calls == [(config, "0000_bootstrap")]
    assert make_url(config.attributes["url_override"]).database == "template1"
    assert config.attributes["version_table_override"] == "alembic_version_bootstrap_user"


@pytest.mark.parametrize("offline", [True, False])
def test_alembic_environment_consumes_bootstrap_url_and_version_overrides(monkeypatch, offline):
    import sqlalchemy
    from alembic import context

    from src.core.database import engine

    url = "postgresql+psycopg://test_admin:test_password@test_host/template1"
    options = {}
    configured = {}
    connection = object()
    config = SimpleNamespace(
        attributes={"url_override": url, "version_table_override": "alembic_version_bootstrap_user"},
        config_file_name=None,
        set_main_option=lambda name, value: options.update({name: value}),
        get_main_option=lambda name: options[name],
    )
    monkeypatch.setattr(context, "config", config, raising=False)
    monkeypatch.setattr(context, "is_offline_mode", lambda: offline)
    monkeypatch.setattr(context, "configure", lambda **kwargs: configured.update(kwargs))
    monkeypatch.setattr(context, "begin_transaction", nullcontext)
    monkeypatch.setattr(context, "run_migrations", lambda: None)
    monkeypatch.setattr(engine, "_build_url", lambda **kwargs: pytest.fail("Bootstrap must bypass service credentials"))

    def create_engine(actual_url, **kwargs):
        assert actual_url == url
        return SimpleNamespace(connect=lambda: nullcontext(connection))

    monkeypatch.setattr(sqlalchemy, "create_engine", create_engine)
    runpy.run_path(str(Path(__file__).parents[1] / "src/core/database/migrations/env.py"))

    assert options["sqlalchemy.url"] == url
    assert configured["version_table"] == "alembic_version_bootstrap_user"
    if offline:
        assert configured["url"] == url
    else:
        assert configured["connection"] is connection
