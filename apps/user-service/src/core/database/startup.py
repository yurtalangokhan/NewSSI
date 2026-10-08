"""Database startup bootstrap for user-service."""

from __future__ import annotations

from collections.abc import Iterator
import contextlib
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from config_manager import env
import psycopg
from sqlalchemy.engine import URL

from src.core.observability import get_logger, retry_sync

logger = get_logger(__name__)

# A stable, service-specific key. Two replicas starting together used to run
# CREATE DATABASE and alembic upgrade concurrently with no coordination,
# which blocked horizontal scaling and could corrupt the schema.
MIGRATION_LOCK_KEY = 0x7573_6572  # "user"


@contextlib.contextmanager
def _migration_lock() -> Iterator[None]:
    """Hold a Postgres session advisory lock for the startup migration.

    Acquired on the service's own database, which the bootstrap migration
    guarantees to exist before the lock is taken.
    """
    settings = env
    with psycopg.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER_SERVICE_USER or "user_service",
        password=_resolve_secret(settings.POSTGRES_USER_SERVICE_PASSWORD),
        dbname=_require(settings.POSTGRES_USER_SERVICE_DB, "POSTGRES_USER_SERVICE_DB"),
        autocommit=True,
        connect_timeout=5,
    ) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
        try:
            yield
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_KEY,))


def _require(value: object, name: str) -> str:
    if value is None or value == "":
        raise ValueError(f"Required environment variable {name} is not set")
    return str(value)


def _resolve_secret(value) -> str:
    """Extract plain text from SecretStr or str, return empty string for None."""
    if value is None:
        return ""
    if hasattr(value, "get_secret_value"):
        return value.get_secret_value()
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
    settings = env
    current = "unknown"
    try:
        with psycopg.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER_SERVICE_USER,
            password=_resolve_secret(settings.POSTGRES_USER_SERVICE_PASSWORD),
            dbname=_require(settings.POSTGRES_USER_SERVICE_DB, "POSTGRES_USER_SERVICE_DB"),
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


def run_database_bootstrap() -> None:
    """Run the bootstrap migration against the maintenance database.

    The first alembic revision (``0000_bootstrap``) creates the service login
    role and database; it runs here with the admin role (from
    ``POSTGRES_ADMIN_USER``/``POSTGRES_ADMIN_PASSWORD``) against the always
    present ``template1`` maintenance database, because the service database
    may not exist yet. Every later connection uses the service's own
    credentials.
    """
    settings = env
    alembic_cfg = _build_alembic_config()
    alembic_cfg.attributes["url_override"] = URL.create(
        drivername="postgresql+psycopg",
        username=_require(settings.POSTGRES_ADMIN_USER, "POSTGRES_ADMIN_USER"),
        password=_resolve_secret(settings.POSTGRES_ADMIN_PASSWORD) or None,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database="template1",
    ).render_as_string(hide_password=False)
    alembic_cfg.attributes["version_table_override"] = "alembic_version_bootstrap_user"
    command.upgrade(alembic_cfg, "0000_bootstrap")


def run_startup_migrations() -> None:
    """Ensure the service database exists and apply Alembic migrations."""
    retry_sync(
        run_database_bootstrap,
        operation_name="bootstrap_database",
        dependency="postgres",
    )
    with _migration_lock():
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
