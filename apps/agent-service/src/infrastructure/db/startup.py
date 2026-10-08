"""Database startup bootstrap for agent-service."""

from __future__ import annotations

from collections.abc import Iterator
import contextlib
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from config_manager import env
import psycopg
from pydantic import SecretStr
from sqlalchemy.engine import URL

from core.observability.logger import get_logger
from core.observability.observability import retry_sync

logger = get_logger(__name__)

# A stable, service-specific key. Two replicas starting together used to run
# CREATE DATABASE and alembic upgrade concurrently with no coordination,
# which blocked horizontal scaling and could corrupt the schema.
MIGRATION_LOCK_KEY = 0x6167_656E  # "agen"


def _require(value: object, name: str) -> str:
    if value is None or value == "":
        raise ValueError(f"Required environment variable {name} is not set")
    return str(value)


def _require_secret(value: SecretStr | str | None, name: str) -> str:
    """Return the plaintext of a required secret setting.

    ``str()`` on a ``SecretStr`` yields ``'**********'``; psycopg would send that
    masked literal as the password. Unwrap explicitly instead.
    """
    plaintext = value.get_secret_value() if isinstance(value, SecretStr) else value
    if not plaintext:
        raise ValueError(f"Required environment variable {name} is not set")
    return plaintext


@contextlib.contextmanager
def _migration_lock() -> Iterator[None]:
    """Hold a Postgres session advisory lock for the startup migration.

    Acquired on the service's own database, which the bootstrap migration
    guarantees to exist before the lock is taken.
    """
    with psycopg.connect(
        host=_require(env.POSTGRES_HOST, "POSTGRES_HOST"),
        port=int(_require(env.POSTGRES_PORT, "POSTGRES_PORT")),
        user=_require(env.POSTGRES_AGENT_SERVICE_USER, "POSTGRES_AGENT_SERVICE_USER"),
        password=_require_secret(env.POSTGRES_AGENT_SERVICE_PASSWORD, "POSTGRES_AGENT_SERVICE_PASSWORD"),
        dbname=_require(env.POSTGRES_AGENT_SERVICE_DB, "POSTGRES_AGENT_SERVICE_DB"),
        autocommit=True,
        connect_timeout=5,
    ) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
        try:
            yield
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_KEY,))


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
        str(service_root / "src/infrastructure/db/migrations"),
    )
    alembic_cfg.set_main_option("prepend_sys_path", str(service_root / "src"))
    alembic_cfg.attributes["configure_logger"] = False
    return alembic_cfg


def _migration_revision_state(alembic_cfg: Config) -> tuple[str, str]:
    current = "unknown"
    try:
        with psycopg.connect(
            host=_require(env.POSTGRES_HOST, "POSTGRES_HOST"),
            port=int(_require(env.POSTGRES_PORT, "POSTGRES_PORT")),
            user=_require(env.POSTGRES_AGENT_SERVICE_USER, "POSTGRES_AGENT_SERVICE_USER"),
            password=_require_secret(env.POSTGRES_AGENT_SERVICE_PASSWORD, "POSTGRES_AGENT_SERVICE_PASSWORD"),
            dbname=_require(env.POSTGRES_AGENT_SERVICE_DB, "POSTGRES_AGENT_SERVICE_DB"),
            connect_timeout=5,
        ) as conn:
            rows = conn.execute("SELECT version_num FROM alembic_version_agent").fetchall()
            current = ",".join(sorted(row[0] for row in rows)) if rows else "base"
    except (psycopg.Error, OSError) as exc:  # pragma: no cover - defensive startup diagnostics
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
    alembic_cfg = _build_alembic_config()
    alembic_cfg.attributes["url_override"] = _admin_maintenance_url()
    alembic_cfg.attributes["version_table_override"] = "alembic_version_bootstrap_agent"
    command.upgrade(alembic_cfg, "0000_bootstrap")


def _admin_maintenance_url() -> str:
    """Build the admin URL for the ``template1`` maintenance database."""
    return URL.create(
        drivername="postgresql+psycopg",
        username=_require(env.POSTGRES_ADMIN_USER, "POSTGRES_ADMIN_USER"),
        password=_require_secret(env.POSTGRES_ADMIN_PASSWORD, "POSTGRES_ADMIN_PASSWORD"),
        host=_require(env.POSTGRES_HOST, "POSTGRES_HOST"),
        port=int(_require(env.POSTGRES_PORT, "POSTGRES_PORT")),
        database="template1",
    ).render_as_string(hide_password=False)


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
        logger.info("Agent service database migration check: current=%s target=%s", current, target)
        retry_sync(
            lambda: command.upgrade(alembic_cfg, "head"),
            operation_name="run_migrations",
            dependency="postgres",
        )
        current, target = _migration_revision_state(alembic_cfg)
        logger.info("Agent service database migrations completed: current=%s target=%s", current, target)
