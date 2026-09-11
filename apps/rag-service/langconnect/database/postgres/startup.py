"""Database startup bootstrap for LangConnect."""

from __future__ import annotations

from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql

from langconnect import config
from langconnect.observability import get_logger, retry_sync

logger = get_logger(__name__)


def _service_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "alembic.ini").exists():
            return parent
    raise RuntimeError("Could not locate rag-service alembic.ini")


def _build_alembic_config() -> Config:
    service_root = _service_root()
    alembic_cfg = Config(str(service_root / "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location",
        str(service_root / "langconnect/database/postgres/migrations"),
    )
    alembic_cfg.set_main_option("prepend_sys_path", str(service_root))
    alembic_cfg.attributes["configure_logger"] = False
    return alembic_cfg


def _migration_revision_state(alembic_cfg: Config) -> tuple[str, str]:
    current = "unknown"
    try:
        with psycopg.connect(
            host=config.POSTGRES_HOST,
            port=config.POSTGRES_PORT,
            user=config.POSTGRES_USER,
            password=config.POSTGRES_PASSWORD,
            dbname=config.POSTGRES_DB,
            connect_timeout=5,
        ) as conn:
            rows = conn.execute("SELECT version_num FROM alembic_version_langconnect").fetchall()
            current = ",".join(sorted(row[0] for row in rows)) if rows else "base"
    except Exception as exc:  # pragma: no cover - defensive startup diagnostics
        current = f"unknown ({exc})"

    script = ScriptDirectory.from_config(alembic_cfg)
    heads = script.get_heads()
    target = ",".join(sorted(heads)) if heads else "base"
    return current, target


def ensure_database_exists() -> None:
    """Create the configured service database if it doesn't exist."""
    with psycopg.connect(
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
        dbname="postgres",
        autocommit=True,
        connect_timeout=5,
    ) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (config.POSTGRES_DB,),
        ).fetchone()
        if exists:
            logger.info("LangConnect database already exists: %s", config.POSTGRES_DB)
            return

        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(config.POSTGRES_DB)))
        logger.info("Created LangConnect database: %s", config.POSTGRES_DB)


def run_startup_migrations() -> None:
    """Ensure the service database exists and apply Alembic migrations."""
    retry_sync(
        ensure_database_exists,
        operation_name="ensure_database",
        dependency="postgres",
    )
    alembic_cfg = _build_alembic_config()
    current, target = _migration_revision_state(alembic_cfg)
    logger.info("LangConnect database migration check: current=%s target=%s", current, target)
    retry_sync(
        lambda: command.upgrade(alembic_cfg, "head"),
        operation_name="run_migrations",
        dependency="postgres",
    )
    current, target = _migration_revision_state(alembic_cfg)
    logger.info("LangConnect database migrations completed: current=%s target=%s", current, target)
