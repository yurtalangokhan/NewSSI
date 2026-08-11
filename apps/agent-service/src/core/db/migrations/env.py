"""Alembic environment configuration.

Reads DB credentials from ``core.settings`` (which honours environment
variables), so ``alembic.ini`` never contains real credentials.

Usage
-----
.. code-block:: bash

   # inside the agent-service-toolkit/ project root
   alembic upgrade head
   alembic revision --autogenerate -m "add foo table"
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection

from core.db.engine import _build_url  # noqa: E402

# ── Import the shared metadata so Alembic can diff models vs DB ──
from core.db.models import Base, register_external_models  # noqa: E402

register_external_models()

# Alembic Config object — gives access to alembic.ini values.
config = context.config

# Use a dedicated version table so agent-service migrations
# don't collide with other projects sharing the same database
# (e.g. langconnect).
VERSION_TABLE = "alembic_version_agent"

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData for 'autogenerate' support
target_metadata = Base.metadata


def exclude_embedding(obj, name, type_, reflected, compare_to):
    """Exclude langchain_pg_embedding from autogenerate — PGVector manages it at runtime."""
    if type_ == "table" and name == "langchain_pg_embedding":
        return False
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_url() -> str:
    """Return a sync DB URL for Alembic's migration runner."""
    return _build_url(driver="psycopg")


# ---------------------------------------------------------------------------
# Offline migrations  (--sql mode, generates SQL script)
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.  Calls to
    ``context.execute()`` emit the given string to the script output.
    """
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=VERSION_TABLE,
        include_object=exclude_embedding,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migrations  (default — connects to the real DB)
# ---------------------------------------------------------------------------


def do_run_migrations(connection: Connection) -> None:
    """Configure context and run migration steps inside a connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # compare_type detects column-type changes (e.g. String→Text)
        compare_type=True,
        # render_as_batch keeps ALTER TABLE compatible with certain DBs
        render_as_batch=True,
        version_table=VERSION_TABLE,
        include_object=exclude_embedding,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using a sync engine.

    We use a plain *sync* engine (psycopg driver) because Alembic's
    migration runner is synchronous.
    """
    from sqlalchemy import create_engine

    connectable = create_engine(
        _get_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)

    connectable.dispose()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
