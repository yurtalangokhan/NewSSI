"""Add project table and project_id on thread.

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-21
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_tables = set(inspector.get_table_names())
    if "project" not in existing_tables:
        op.create_table(
            "project",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("instructions", sa.Text(), nullable=True),
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("project")}
    if "idx_project_user_id" not in existing_indexes:
        op.create_index("idx_project_user_id", "project", ["user_id"], unique=False)
    if "idx_project_user_id_created_at" not in existing_indexes:
        op.create_index(
            "idx_project_user_id_created_at",
            "project",
            ["user_id", "created_at"],
            unique=False,
        )

    thread_columns = {col["name"] for col in inspector.get_columns("thread")}
    if "project_id" not in thread_columns:
        op.add_column("thread", sa.Column("project_id", sa.Integer(), nullable=True))

    fk_names = {fk["name"] for fk in inspector.get_foreign_keys("thread") if fk.get("name")}
    if "fk_thread_project_id_project" not in fk_names:
        op.create_foreign_key(
            "fk_thread_project_id_project",
            "thread",
            "project",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    op.drop_constraint("fk_thread_project_id_project", "thread", type_="foreignkey")
    op.drop_column("thread", "project_id")

    op.drop_index("idx_project_user_id_created_at", table_name="project")
    op.drop_index("idx_project_user_id", table_name="project")
    op.drop_table("project")
