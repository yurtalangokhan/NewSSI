"""Database startup bootstrap for agent-service."""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql

from core.settings import settings

logger = logging.getLogger(__name__)


def _require(value: object, name: str) -> str:
    if value is None or value == "":
        raise ValueError(f"Required environment variable {name} is not set")
    return str(value)


def _service_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "alembic.ini").exists():
            return parent
    raise RuntimeError("Could not locate agent-service alembic.ini")


def _build_alembic_config() -> Config:
    service_root = _service_root()
    alembic_cfg = Config(str(service_root / "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location",
        str(service_root / "src/core/db/migrations"),
    )
    alembic_cfg.set_main_option("prepend_sys_path", str(service_root / "src"))
    alembic_cfg.attributes["configure_logger"] = False
    return alembic_cfg


def _migration_revision_state(alembic_cfg: Config) -> tuple[str, str]:
    current = "unknown"
    try:
        with psycopg.connect(
            host=_require(settings.POSTGRES_HOST, "POSTGRES_HOST"),
            port=int(_require(settings.POSTGRES_PORT, "POSTGRES_PORT")),
            user=_require(settings.POSTGRES_USER, "POSTGRES_USER"),
            password=_require(settings.POSTGRES_PASSWORD, "POSTGRES_PASSWORD"),
            dbname=_require(settings.POSTGRES_DB, "POSTGRES_DB"),
            connect_timeout=5,
        ) as conn:
            rows = conn.execute("SELECT version_num FROM alembic_version_agent").fetchall()
            current = ",".join(sorted(row[0] for row in rows)) if rows else "base"
    except Exception as exc:  # pragma: no cover - defensive startup diagnostics
        current = f"unknown ({exc})"

    script = ScriptDirectory.from_config(alembic_cfg)
    heads = script.get_heads()
    target = ",".join(sorted(heads)) if heads else "base"
    return current, target


def ensure_database_exists() -> None:
    """Create the configured service database if it doesn't exist."""
    database = _require(settings.POSTGRES_DB, "POSTGRES_DB")
    password = _require(settings.POSTGRES_PASSWORD, "POSTGRES_PASSWORD")

    with psycopg.connect(
        host=_require(settings.POSTGRES_HOST, "POSTGRES_HOST"),
        port=int(_require(settings.POSTGRES_PORT, "POSTGRES_PORT")),
        user=_require(settings.POSTGRES_USER, "POSTGRES_USER"),
        password=password,
        dbname="postgres",
        autocommit=True,
        connect_timeout=5,
    ) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (database,),
        ).fetchone()
        if exists:
            logger.info("Agent service database already exists: %s", database)
            return

        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        logger.info("Created agent service database: %s", database)


def run_startup_migrations() -> None:
    """Ensure the service database exists and apply Alembic migrations."""
    ensure_database_exists()
    alembic_cfg = _build_alembic_config()
    current, target = _migration_revision_state(alembic_cfg)
    logger.info("Agent service database migration check: current=%s target=%s", current, target)
    command.upgrade(alembic_cfg, "head")
    current, target = _migration_revision_state(alembic_cfg)
    logger.info(
        "Agent service database migrations completed: current=%s target=%s", current, target
    )
