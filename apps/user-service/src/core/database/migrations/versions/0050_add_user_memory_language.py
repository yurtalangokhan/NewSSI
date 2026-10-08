"""add language column to user_memory

Records the BCP-47 tag agent-service's extractor had the model declare for a
batch of facts. Until now nothing stored which language a fact was written in,
so a fact written in the wrong one was simply never recalled -- recall matches
a query against stored facts with a language-aware lexical pass, which cannot
match across languages -- and no signal anywhere said so.

Nullable with no default and no backfill, on purpose: existing rows and facts a
user typed in by hand have no declared language, and "unknown" is not the same
as any particular language. Filling them in would record a guess as an
observation.

Revision ID: 0050
Revises: 0049
Create Date: 2026-09-23

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: RFC 5646 tags fit well within this; matches the bounded-varchar style the
#: table already uses for `source`.
_LANGUAGE_LENGTH = 35


def _has_column(table: str, column: str) -> bool:
    inspector = inspect(op.get_bind())
    if not inspector.has_table(table):
        return False
    return any(existing["name"] == column for existing in inspector.get_columns(table))


def upgrade() -> None:
    if not _has_column("user_memory", "language"):
        op.add_column(
            "user_memory",
            sa.Column("language", sa.String(_LANGUAGE_LENGTH), nullable=True),
        )


def downgrade() -> None:
    if _has_column("user_memory", "language"):
        op.drop_column("user_memory", "language")
