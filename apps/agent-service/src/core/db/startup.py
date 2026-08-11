"""Database startup bootstrap for agent-service."""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
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
    alembic_cfg = Config(str(_service_root() / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")
    logger.info("Agent service database migrations are at head.")
