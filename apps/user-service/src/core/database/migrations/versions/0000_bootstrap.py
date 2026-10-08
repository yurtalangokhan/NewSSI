"""bootstrap - create the service login role and database

Revision ID: 0000
Revises: None
Create Date: 2026-09-18

The startup's first alembic invocation runs this revision against the
``template1`` maintenance database (or ``postgres`` for existing callers) with the admin role (from
``POSTGRES_ADMIN_USER``/``POSTGRES_ADMIN_PASSWORD``): it creates the login
role from ``POSTGRES_USER_SERVICE_USER``/``..._PASSWORD`` and the database
named by ``POSTGRES_USER_SERVICE_DB`` owned by that role. Every later
connection uses the service's own credentials.

When the chain runs against the service's own database, this revision is a
no-op (the role and database exist there by definition); it is only stamped
so the chain stays linear.
"""

from alembic import op
from config_manager import env
from sqlalchemy import text

revision = "0000_bootstrap"
down_revision = None
branch_labels = None
depends_on = None

_MAINTENANCE_DATABASES = {"postgres", "template1"}


def _env(name: str) -> str:
    return env.require(name)


def _literal(value: str) -> str:
    """Quote a value as a SQL string literal (utility DDL takes no params)."""
    return "'" + value.replace("'", "''") + "'"


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _on_maintenance_database() -> bool:
    return op.get_bind().execute(text("SELECT current_database()")).scalar() in _MAINTENANCE_DATABASES


def upgrade() -> None:
    if not _on_maintenance_database():
        return

    user = _env("POSTGRES_USER_SERVICE_USER")
    password = _env("POSTGRES_USER_SERVICE_PASSWORD")
    database = _env("POSTGRES_USER_SERVICE_DB")

    with op.get_context().autocommit_block():
        bind = op.get_bind()
        role_exists = bind.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :user"), {"user": user}).fetchone()
        if role_exists:
            bind.execute(text(f"ALTER ROLE {_identifier(user)} WITH PASSWORD {_literal(password)}"))
        else:
            bind.execute(text(f"CREATE ROLE {_identifier(user)} LOGIN PASSWORD {_literal(password)}"))

        db_exists = bind.execute(text("SELECT 1 FROM pg_database WHERE datname = :db"), {"db": database}).fetchone()
        if not db_exists:
            bind.execute(text(f"CREATE DATABASE {_identifier(database)} OWNER {_identifier(user)}"))
