"""drop users is_superuser column and add missing permissions

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-13 00:00:00.000000
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


PERMISSIONS: tuple[tuple[str, str, str, str, str, str, bool], ...] = (
    (
        "user:impersonate",
        "Impersonate Users",
        "user",
        "user-service",
        "impersonate",
        "access",
        True,
    ),
    (
        "mail_config:create",
        "Create Mail Configurations",
        "mail_config",
        "agent-service",
        "create",
        "tools",
        False,
    ),
    (
        "mail_config:delete",
        "Delete Mail Configurations",
        "mail_config",
        "agent-service",
        "delete",
        "tools",
        False,
    ),
    (
        "mail_config:read",
        "Read Mail Configurations",
        "mail_config",
        "agent-service",
        "read",
        "tools",
        False,
    ),
    (
        "mail_config:send",
        "Send Mail With Configurations",
        "mail_config",
        "agent-service",
        "send",
        "tools",
        False,
    ),
    (
        "mail_config:test",
        "Test Mail Configurations",
        "mail_config",
        "agent-service",
        "test",
        "tools",
        False,
    ),
    (
        "mail_config:update",
        "Update Mail Configurations",
        "mail_config",
        "agent-service",
        "update",
        "tools",
        False,
    ),
)


def _insert_permissions() -> None:
    for name, label, entity, service, action, feature, is_system in PERMISSIONS:
        op.execute(
            sa.text(
                """
                INSERT INTO permissions
                    (name, label, description, entity, service, action, feature, is_system)
                VALUES
                    (:name, :label, NULL, :entity, :service, :action, :feature, :is_system)
                ON CONFLICT (name) DO UPDATE SET
                    label = EXCLUDED.label,
                    entity = EXCLUDED.entity,
                    service = EXCLUDED.service,
                    action = EXCLUDED.action,
                    feature = EXCLUDED.feature,
                    is_system = EXCLUDED.is_system
                """
            ).bindparams(
                name=name,
                label=label,
                entity=entity,
                service=service,
                action=action,
                feature=feature,
                is_system=is_system,
            )
        )


def _add_role_permissions(role_name: str, permissions: tuple[str, ...]) -> None:
    permissions_json = json.dumps(list(permissions))
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET permissions = (
                SELECT jsonb_agg(permission ORDER BY permission)
                FROM (
                    SELECT DISTINCT permission
                    FROM (
                        SELECT jsonb_array_elements_text(COALESCE(permissions, '[]'::jsonb))
                            AS permission
                        FROM roles
                        WHERE name = :role_name
                        UNION ALL
                        SELECT jsonb_array_elements_text(CAST(:permissions_json AS jsonb))
                            AS permission
                    ) AS combined
                ) AS distinct_permissions
            )
            WHERE name = :role_name
            """
        ).bindparams(role_name=role_name, permissions_json=permissions_json)
    )


def upgrade() -> None:
    _insert_permissions()
    _add_role_permissions("access-admin", ("user:impersonate",))
    _add_role_permissions(
        "tooling-admin",
        (
            "mail_config:create",
            "mail_config:delete",
            "mail_config:read",
            "mail_config:send",
            "mail_config:test",
            "mail_config:update",
        ),
    )
    _add_role_permissions(
        "tooling-user",
        (
            "mail_config:create",
            "mail_config:delete",
            "mail_config:read",
            "mail_config:send",
            "mail_config:test",
            "mail_config:update",
        ),
    )
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS is_superuser")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_superuser BOOLEAN DEFAULT false NOT NULL"
    )
