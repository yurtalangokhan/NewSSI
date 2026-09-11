"""Database startup bootstrap for user-service."""

from __future__ import annotations

from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql

from src.config import get_settings
from src.core.observability import get_logger, retry_sync

logger = get_logger(__name__)


def _require(value: object, name: str) -> str:
    if value is None or value == "":
        raise ValueError(f"Required environment variable {name} is not set")
    return str(value)


def _service_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "alembic.ini").exists():
            return parent
    raise RuntimeError("Could not locate user-service alembic.ini")


def _build_alembic_config() -> Config:
    service_root = _service_root()
    alembic_cfg = Config(str(service_root / "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location",
        str(service_root / "src/core/database/migrations"),
    )
    alembic_cfg.set_main_option("prepend_sys_path", str(service_root / "src"))
    alembic_cfg.attributes["configure_logger"] = False
    return alembic_cfg


def _migration_revision_state(alembic_cfg: Config) -> tuple[str, str]:
    settings = get_settings()
    current = "unknown"
    try:
        with psycopg.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER or "user_service",
            password=settings.POSTGRES_PASSWORD or "user_service_pass",
            dbname=_require(settings.POSTGRES_DB or "user_service", "POSTGRES_DB"),
            connect_timeout=5,
        ) as conn:
            rows = conn.execute("SELECT version_num FROM alembic_version_user").fetchall()
            current = ",".join(sorted(row[0] for row in rows)) if rows else "base"
    except Exception as exc:  # pragma: no cover - defensive startup diagnostics
        current = f"unknown ({exc})"

    script = ScriptDirectory.from_config(alembic_cfg)
    heads = script.get_heads()
    target = ",".join(sorted(heads)) if heads else "base"
    return current, target


def ensure_database_exists() -> None:
    """Create the configured service database if it doesn't exist."""
    settings = get_settings()
    database = _require(settings.POSTGRES_DB or "user_service", "POSTGRES_DB")

    with psycopg.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER or "user_service",
        password=settings.POSTGRES_PASSWORD or "user_service_pass",
        dbname="postgres",
        autocommit=True,
        connect_timeout=5,
    ) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (database,),
        ).fetchone()
        if exists:
            logger.info("User service database already exists: %s", database)
            return

        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        logger.info("Created user service database: %s", database)


def run_startup_migrations() -> None:
    """Ensure the service database exists and apply Alembic migrations."""
    retry_sync(
        ensure_database_exists,
        operation_name="ensure_database",
        dependency="postgres",
    )
    alembic_cfg = _build_alembic_config()
    current, target = _migration_revision_state(alembic_cfg)
    logger.info("User service database migration check: current=%s target=%s", current, target)
    retry_sync(
        lambda: command.upgrade(alembic_cfg, "head"),
        operation_name="run_migrations",
        dependency="postgres",
    )
    current, target = _migration_revision_state(alembic_cfg)
    logger.info("User service database migrations completed: current=%s target=%s", current, target)
