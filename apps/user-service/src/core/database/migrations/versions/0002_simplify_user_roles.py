"""simplify user roles

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET role = CASE
            WHEN role IN ('admin', 'ADMIN') THEN 'admin'
            ELSE 'enduser'
        END
        """
    )
    op.execute(
        """
        INSERT INTO roles (name, description, permissions, is_builtin)
        VALUES ('enduser', 'Standard end user access', '["content:read"]', true)
        ON CONFLICT (name) DO UPDATE SET
            description = EXCLUDED.description,
            permissions = EXCLUDED.permissions,
            is_builtin = EXCLUDED.is_builtin
        """
    )
    op.execute(
        """
        DELETE FROM roles
        WHERE name NOT IN ('admin', 'enduser')
        """
    )
    op.alter_column(
        "users",
        "role",
        existing_type=sa.String(50),
        server_default="'enduser'",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "role",
        existing_type=sa.String(50),
        server_default="'basic'",
        existing_nullable=False,
    )
    op.execute("UPDATE users SET role = 'basic' WHERE role = 'enduser'")
    op.execute(
        """
        INSERT INTO roles (name, description, permissions, is_builtin)
        VALUES
            ('basic', 'Standard user with basic access', '["content:read"]', true),
            ('limited', 'Limited user with minimal access', '["content:read"]', true),
            ('curator', 'Curator for assigned content', '["users:read", "content:read", "content:write"]', true),
            ('global_curator', 'Global curator with content management', '["users:read", "users:update", "content:read", "content:write", "content:delete"]', true)
        ON CONFLICT (name) DO NOTHING
        """
    )
    op.execute("DELETE FROM roles WHERE name = 'enduser'")
