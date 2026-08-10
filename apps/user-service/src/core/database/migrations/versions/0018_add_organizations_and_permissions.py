"""Add organization management and resource permissions.

Revision ID: 0018
Revises: 0017
Create Date: 2024-01-15 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create organizations table
    op.create_table(
        "organizations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_organizations_name", "organizations", ["name"])
    op.create_index("ix_organizations_code", "organizations", ["code"])
    op.create_index("ix_organizations_parent_id", "organizations", ["parent_id"])
    op.create_index("ix_organizations_path", "organizations", ["path"])
    op.create_index("ix_organizations_level", "organizations", ["level"])
    op.execute(
        "CREATE UNIQUE INDEX uq_organizations_single_root "
        "ON organizations ((parent_id IS NULL)) WHERE parent_id IS NULL"
    )

    # Create user_organizations table (many-to-many)
    op.create_table(
        "user_organizations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_in_org", sa.String(length=100), nullable=False, server_default="'member'"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_organizations_user_id", "user_organizations", ["user_id"])
    op.create_index(
        "ix_user_organizations_organization_id", "user_organizations", ["organization_id"]
    )
    op.create_index("ix_user_organizations_role_in_org", "user_organizations", ["role_in_org"])
    op.create_index(
        "idx_user_org_unique",
        "user_organizations",
        ["user_id", "organization_id"],
        unique=True,
    )
    op.create_index(
        "idx_user_org_role",
        "user_organizations",
        ["user_id", "organization_id", "role_in_org"],
    )

    # Create resource_permissions table
    op.create_table(
        "resource_permissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("resource_name", sa.String(length=255), nullable=False, server_default="''"),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("permission_level", sa.String(length=20), nullable=False),
        sa.Column("is_inherited", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(organization_id IS NOT NULL AND user_id IS NULL) OR "
            "(organization_id IS NULL AND user_id IS NOT NULL)",
            name="check_exclusive_org_or_user",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_resource_permissions_resource_type", "resource_permissions", ["resource_type"]
    )
    op.create_index("ix_resource_permissions_resource_id", "resource_permissions", ["resource_id"])
    op.create_index(
        "ix_resource_permissions_organization_id",
        "resource_permissions",
        ["organization_id"],
    )
    op.create_index("ix_resource_permissions_user_id", "resource_permissions", ["user_id"])
    op.create_index(
        "ix_resource_permissions_permission_level",
        "resource_permissions",
        ["permission_level"],
    )
    op.create_index(
        "idx_resource_type_id",
        "resource_permissions",
        ["resource_type", "resource_id"],
    )
    # Unique constraint for organization permissions
    op.execute(
        """
        CREATE UNIQUE INDEX idx_resource_perm_org_unique
        ON resource_permissions (resource_type, resource_id, organization_id)
        WHERE organization_id IS NOT NULL
        """
    )
    # Unique constraint for user permissions
    op.execute(
        """
        CREATE UNIQUE INDEX idx_resource_perm_user_unique
        ON resource_permissions (resource_type, resource_id, user_id)
        WHERE user_id IS NOT NULL
        """
    )

    # Create permission_audit_logs table
    op.create_table(
        "permission_audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("resource_name", sa.String(length=255), nullable=False, server_default="''"),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_name", sa.String(length=255), nullable=False, server_default="''"),
        sa.Column("permission_level", sa.String(length=20), nullable=True),
        sa.Column("old_permission_level", sa.String(length=20), nullable=True),
        sa.Column("performed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "performed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_permission_audit_logs_action", "permission_audit_logs", ["action"])
    op.create_index(
        "ix_permission_audit_logs_resource_type", "permission_audit_logs", ["resource_type"]
    )
    op.create_index(
        "ix_permission_audit_logs_resource_id", "permission_audit_logs", ["resource_id"]
    )
    op.create_index("ix_permission_audit_logs_target_id", "permission_audit_logs", ["target_id"])
    op.create_index(
        "ix_permission_audit_logs_performed_at",
        "permission_audit_logs",
        ["performed_at"],
    )


def downgrade() -> None:
    op.drop_table("permission_audit_logs")
    op.drop_table("resource_permissions")
    op.drop_table("user_organizations")
    op.drop_table("organizations")
