"""Database startup bootstrap for user-service."""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql

from src.config import get_settings

logger = logging.getLogger(__name__)


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
    return alembic_cfg


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
    ensure_database_exists()
    command.upgrade(_build_alembic_config(), "head")
    logger.info("User service database migrations are at head.")
