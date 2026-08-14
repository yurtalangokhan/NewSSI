"""repair missing organization tables after rebased revision graph

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-14 00:00:00.000000

"""

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS organizations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            code VARCHAR(100) NOT NULL UNIQUE,
            description TEXT NULL,
            parent_id UUID NULL REFERENCES organizations(id) ON DELETE CASCADE,
            path VARCHAR(1000) NOT NULL,
            level INTEGER NOT NULL DEFAULT 0,
            order_index INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT true,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            created_by UUID NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_organizations_name ON organizations (name)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_organizations_code ON organizations (code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_organizations_parent_id ON organizations (parent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_organizations_path ON organizations (path)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_organizations_level ON organizations (level)")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_organizations_single_root
        ON organizations ((parent_id IS NULL))
        WHERE parent_id IS NULL
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_organizations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            role_in_org VARCHAR(100) NOT NULL DEFAULT 'member',
            is_primary BOOLEAN NOT NULL DEFAULT false,
            is_active BOOLEAN NOT NULL DEFAULT true,
            joined_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            assigned_by UUID NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_organizations_user_id ON user_organizations (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_organizations_organization_id "
        "ON user_organizations (organization_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_organizations_role_in_org "
        "ON user_organizations (role_in_org)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_org_unique "
        "ON user_organizations (user_id, organization_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_org_role "
        "ON user_organizations (user_id, organization_id, role_in_org)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS resource_permissions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            resource_type VARCHAR(50) NOT NULL,
            resource_id VARCHAR(255) NOT NULL,
            resource_name VARCHAR(255) NOT NULL DEFAULT '',
            organization_id UUID NULL REFERENCES organizations(id) ON DELETE CASCADE,
            user_id UUID NULL REFERENCES users(id) ON DELETE CASCADE,
            permission_level VARCHAR(20) NOT NULL,
            is_inherited BOOLEAN NOT NULL DEFAULT false,
            granted_by UUID NULL,
            granted_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            expires_at TIMESTAMP WITH TIME ZONE NULL,
            CONSTRAINT check_exclusive_org_or_user CHECK (
                (organization_id IS NOT NULL AND user_id IS NULL)
                OR (organization_id IS NULL AND user_id IS NOT NULL)
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_resource_permissions_resource_type "
        "ON resource_permissions (resource_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_resource_permissions_resource_id "
        "ON resource_permissions (resource_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_resource_permissions_organization_id "
        "ON resource_permissions (organization_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_resource_permissions_user_id "
        "ON resource_permissions (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_resource_permissions_permission_level "
        "ON resource_permissions (permission_level)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_resource_type_id "
        "ON resource_permissions (resource_type, resource_id)"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_resource_perm_org_unique
        ON resource_permissions (resource_type, resource_id, organization_id)
        WHERE organization_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_resource_perm_user_unique
        ON resource_permissions (resource_type, resource_id, user_id)
        WHERE user_id IS NOT NULL
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS permission_audit_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            action VARCHAR(20) NOT NULL,
            permission_id UUID NULL,
            resource_type VARCHAR(50) NOT NULL,
            resource_id VARCHAR(255) NOT NULL,
            resource_name VARCHAR(255) NOT NULL DEFAULT '',
            target_type VARCHAR(20) NOT NULL,
            target_id UUID NOT NULL,
            target_name VARCHAR(255) NOT NULL DEFAULT '',
            permission_level VARCHAR(20) NULL,
            old_permission_level VARCHAR(20) NULL,
            performed_by UUID NULL,
            performed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            ip_address VARCHAR(45) NULL,
            user_agent VARCHAR(500) NULL,
            details JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_permission_audit_logs_action "
        "ON permission_audit_logs (action)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_permission_audit_logs_resource_type "
        "ON permission_audit_logs (resource_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_permission_audit_logs_resource_id "
        "ON permission_audit_logs (resource_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_permission_audit_logs_target_id "
        "ON permission_audit_logs (target_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_permission_audit_logs_performed_at "
        "ON permission_audit_logs (performed_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS organization_layouts (
            organization_id UUID PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
            position_x DOUBLE PRECISION NOT NULL,
            position_y DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT ck_organization_layouts_position_x_bounds
                CHECK (position_x >= -100000000 AND position_x <= 100000000),
            CONSTRAINT ck_organization_layouts_position_y_bounds
                CHECK (position_y >= -100000000 AND position_y <= 100000000)
        )
        """
    )


def downgrade() -> None:
    """Repair migrations are intentionally non-destructive."""
