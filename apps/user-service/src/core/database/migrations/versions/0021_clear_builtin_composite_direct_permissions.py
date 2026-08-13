"""clear built-in composite direct permissions

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-12

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE composite_roles
        SET permissions = '[]'::jsonb
        WHERE name IN ('system-admin', 'enterprise-admin', 'enduser')
        """
    )


def downgrade() -> None:
    # Direct permissions are intentionally not reconstructed. They are legacy
    # data and the authoritative grants live in role_ids feature bundles.
    pass
