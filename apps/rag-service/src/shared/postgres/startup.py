"""Database startup bootstrap for the RAG service."""

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

from src.shared.observability import get_logger, retry_sync

logger = get_logger(__name__)

# A stable, service-specific key. Two replicas starting together used to run
# CREATE DATABASE and alembic upgrade concurrently with no coordination,
# which blocked horizontal scaling and could corrupt the schema.
MIGRATION_LOCK_KEY = 0x7261_6720  # "rag "


def _connect_to_service_database(*, autocommit: bool = False) -> psycopg.Connection:
    """Open a short-lived connection to the service's own database."""
    return psycopg.connect(
        host=env.POSTGRES_HOST,
        port=env.POSTGRES_PORT,
        user=env.POSTGRES_RAG_SERVICE_USER,
        password=env.POSTGRES_RAG_SERVICE_PASSWORD,
        dbname=env.POSTGRES_RAG_SERVICE_DB,
        autocommit=autocommit,
        connect_timeout=5,
    )


@contextlib.contextmanager
def _migration_lock() -> Iterator[None]:
    """Hold a Postgres session advisory lock for the startup migration.

    Acquired on the service's own database, which the bootstrap migration
    guarantees to exist before the lock is taken.
    """
    with _connect_to_service_database(autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
        try:
            yield
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_KEY,))


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
        str(service_root / "src/shared/postgres/migrations"),
    )
    alembic_cfg.set_main_option("prepend_sys_path", str(service_root))
    alembic_cfg.attributes["configure_logger"] = False
    return alembic_cfg


def _adopt_legacy_version_table() -> None:
    """Rename the pre-rename ``alembic_version_langconnect`` table in place.

    A deployment that migrated before the rename keeps its applied revisions
    instead of re-running every migration against an already-migrated schema.
    Connection errors propagate on purpose: swallowing one would let ``upgrade``
    start from an empty ``alembic_version_rag``.
    """
    with _connect_to_service_database() as conn:
        legacy = conn.execute("SELECT to_regclass('alembic_version_langconnect')").fetchone()[0]
        current = conn.execute("SELECT to_regclass('alembic_version_rag')").fetchone()[0]
        if legacy and not current:
            conn.execute("ALTER TABLE alembic_version_langconnect RENAME TO alembic_version_rag")
            logger.info("Renamed legacy alembic_version_langconnect to alembic_version_rag")


def _migration_revision_state(alembic_cfg: Config) -> tuple[str, str]:
    current = "unknown"
    try:
        with _connect_to_service_database() as conn:
            rows = conn.execute("SELECT version_num FROM alembic_version_rag").fetchall()
            current = ",".join(sorted(row[0] for row in rows)) if rows else "base"
    except (
        psycopg.Error,
        OSError,
    ) as exc:  # pragma: no cover - defensive startup diagnostics
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
    alembic_cfg.attributes["url_override"] = URL.create(
        drivername="postgresql+psycopg",
        username=_require_env("POSTGRES_ADMIN_USER"),
        password=_require_env("POSTGRES_ADMIN_PASSWORD"),
        host=env.POSTGRES_HOST,
        port=env.POSTGRES_PORT,
        database="template1",
    ).render_as_string(hide_password=False)
    alembic_cfg.attributes["version_table_override"] = "alembic_version_bootstrap_rag"
    command.upgrade(alembic_cfg, "0000_bootstrap")


def _require_env(name: str) -> str:
    value = getattr(env, name, None)
    if not value:
        raise ValueError(f"Required environment variable {name} is not set")
    return str(value)


def run_startup_migrations() -> None:
    """Ensure the service database exists and apply Alembic migrations."""
    retry_sync(
        run_database_bootstrap,
        operation_name="bootstrap_database",
        dependency="postgres",
    )
    with _migration_lock():
        retry_sync(
            _adopt_legacy_version_table,
            operation_name="adopt_legacy_version_table",
            dependency="postgres",
        )
        alembic_cfg = _build_alembic_config()
        current, target = _migration_revision_state(alembic_cfg)
        logger.info(
            "RAG service database migration check: current=%s target=%s",
            current,
            target,
        )
        retry_sync(
            lambda: command.upgrade(alembic_cfg, "head"),
            operation_name="run_migrations",
            dependency="postgres",
        )
        current, target = _migration_revision_state(alembic_cfg)
        logger.info(
            "RAG service database migrations completed: current=%s target=%s",
            current,
            target,
        )
