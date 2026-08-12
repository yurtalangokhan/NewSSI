"""Database startup bootstrap for LangConnect."""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql

from langconnect import config

logger = logging.getLogger(__name__)


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
    return alembic_cfg


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
    ensure_database_exists()
    command.upgrade(_build_alembic_config(), "head")
    logger.info("LangConnect database migrations are at head.")
