"""baseline: langchain_pg_collection & langchain_pg_embedding

Revision ID: 0001_baseline
Revises: –
Create Date: 2025-01-01 00:00:00.000000

Creates the ``langchain_pg_collection`` and ``langchain_pg_embedding``
tables with their indexes.  Uses ``if_not_exists=True`` so the DDL is
safe to run on databases where the tables are already present.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### langchain_pg_collection ###
    op.create_table(
        "langchain_pg_collection",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("cmetadata", postgresql.JSON(), nullable=True),
        if_not_exists=True,
    )

    # ### langchain_pg_embedding ###
    op.create_table(
        "langchain_pg_embedding",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "collection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "langchain_pg_collection.uuid", ondelete="CASCADE"
            ),
            nullable=True,
        ),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("document", sa.String(), nullable=True),
        sa.Column("cmetadata", postgresql.JSONB(), nullable=True),
        if_not_exists=True,
    )

    # GIN index on cmetadata
    op.create_index(
        "ix_cmetadata_gin",
        "langchain_pg_embedding",
        ["cmetadata"],
        postgresql_using="gin",
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_cmetadata_gin", table_name="langchain_pg_embedding")
    op.drop_table("langchain_pg_embedding")
    op.drop_table("langchain_pg_collection")
