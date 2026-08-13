"""Seed organization page permissions for enterprise administrators.

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-13 00:00:00.000000
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO permissions
            (name, label, description, entity, service, action, is_system)
        VALUES
            ('org:list', 'List Organizations', 'List organizations',
             'organization', 'user-service', 'list', true),
            ('org:read', 'Read Organization', 'View organization details',
             'organization', 'user-service', 'read', true)
        ON CONFLICT (name) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE composite_roles
        SET permissions = (
            SELECT jsonb_agg(permission ORDER BY permission)
            FROM (
                SELECT DISTINCT jsonb_array_elements_text(
                    permissions || '["org:list", "org:read"]'::jsonb
                ) AS permission
            ) AS merged_permissions
        )
        WHERE name = 'enterprise-admin'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE composite_roles
        SET permissions = COALESCE((
            SELECT jsonb_agg(permission ORDER BY permission)
            FROM jsonb_array_elements_text(permissions) AS permission
            WHERE permission NOT IN ('org:list', 'org:read')
        ), '[]'::jsonb)
        WHERE name = 'enterprise-admin'
        """
    )
    op.execute("DELETE FROM permissions WHERE name IN ('org:list', 'org:read')")
