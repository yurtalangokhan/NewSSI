"""Add document table for MinIO-backed file storage.

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_tables = set(inspector.get_table_names())
    if "document" not in existing_tables:
        op.create_table(
            "document",
            sa.Column(
                "id",
                UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("file_id", sa.String(64), nullable=False, unique=True),
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column("filename", sa.Text(), nullable=False),
            sa.Column("mime_type", sa.Text(), nullable=False),
            sa.Column("chat_file_type", sa.Text(), nullable=False, server_default="document"),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("minio_object_key", sa.Text(), nullable=False),
            sa.Column(
                "thread_id",
                UUID(as_uuid=True),
                sa.ForeignKey("thread.thread_id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "project_id",
                sa.Integer(),
                sa.ForeignKey("project.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )

    existing_indexes = set()
    if "document" in existing_tables or "document" not in existing_tables:
        try:
            existing_indexes = {idx["name"] for idx in inspector.get_indexes("document")}
        except Exception:
            pass

    if "ix_document_user_id" not in existing_indexes:
        op.create_index("ix_document_user_id", "document", ["user_id"], unique=False)
    if "ix_document_thread_id" not in existing_indexes:
        op.create_index("ix_document_thread_id", "document", ["thread_id"], unique=False)
    if "ix_document_project_id" not in existing_indexes:
        op.create_index("ix_document_project_id", "document", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_document_project_id", table_name="document")
    op.drop_index("ix_document_thread_id", table_name="document")
    op.drop_index("ix_document_user_id", table_name="document")
    op.drop_table("document")
