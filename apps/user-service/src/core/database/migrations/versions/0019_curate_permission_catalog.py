"""curate permission catalog and add feature dimension

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-11

Prunes the permission catalog to only enforced, real access-control needs
(125 -> 92), adds ``agent:feedback``, backfills the new ``feature`` column, and
removes the pruned permission names from existing role JSONB arrays.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Declared-but-unenforced permissions removed from the catalog.
REMOVED_PERMISSIONS: tuple[str, ...] = (
    # user-service
    "api_key:update",
    "audit_log:export",
    "audit_log:list",
    "audit_log:manage",
    "audit_log:read",
    "group:create",
    "group:delete",
    "group:list",
    "group:manage",
    "group:read",
    "group:update",
    "monitor:alert",
    "monitor:read",
    "permission:create",
    "permission:delete",
    "permission:update",
    "role:create",
    "role:delete",
    "role:update",
    # agent-service
    "agent:share",
    "agent_definition:create",
    "agent_definition:delete",
    "agent_definition:read",
    "agent_definition:update",
    "analytics:export",
    "analytics:read",
    "conversation:delete",
    "conversation:export",
    "conversation:read",
    # rag-service
    "chunk:read",
    "chunk:search",
    "document:update",
    "embedding:read",
    # tools-service
    "tool:read",
)

# (service, entity) -> feature, mirrored from src/core/permissions/features.py.
FEATURE_MAP: dict[tuple[str, str], str] = {
    ("user-service", "user"): "access",
    ("user-service", "role"): "access",
    ("user-service", "permission"): "access",
    ("user-service", "api_key"): "access",
    ("user-service", "group"): "access",
    ("user-service", "audit_log"): "access",
    ("agent-service", "agent"): "agents",
    ("agent-service", "agent_definition"): "agents",
    ("agent-service", "assistant"): "agents",
    ("agent-service", "persona"): "agents",
    ("agent-service", "chat"): "chat",
    ("agent-service", "conversation"): "chat",
    ("agent-service", "thread"): "chat",
    ("agent-service", "run"): "chat",
    ("rag-service", "collection"): "knowledge",
    ("rag-service", "document"): "knowledge",
    ("rag-service", "chunk"): "knowledge",
    ("rag-service", "embedding"): "knowledge",
    ("rag-service", "graph"): "knowledge",
    ("tools-service", "tool"): "tools",
    ("agent-service", "mcp_provider"): "tools",
    ("agent-service", "mcp_tool"): "tools",
    ("agent-service", "datasource"): "tools",
    ("agent-service", "web_search"): "tools",
    ("agent-service", "provider"): "tools",
    ("agent-service", "schedule"): "tools",
    ("agent-service", "project"): "workspace",
    ("user-service", "memory"): "workspace",
    ("user-service", "settings"): "workspace",
    ("system", "system.settings"): "system",
    ("system", "monitor"): "system",
    ("agent-service", "analytics"): "system",
}


def upgrade() -> None:
    bind = op.get_bind()

    columns = {col["name"] for col in sa.inspect(bind).get_columns("permissions")}
    if "feature" not in columns:
        op.add_column(
            "permissions",
            sa.Column("feature", sa.String(50), nullable=False, server_default="system"),
        )

    for (service, entity), feature in FEATURE_MAP.items():
        op.execute(
            sa.text(
                "UPDATE permissions SET feature = :feature "
                "WHERE service = :service AND entity = :entity"
            ).bindparams(feature=feature, service=service, entity=entity)
        )

    op.execute(
        sa.text(
            "INSERT INTO permissions "
            "(name, label, description, entity, service, action, feature, is_system, created_at) "
            "VALUES (:name, :label, NULL, :entity, :service, :action, :feature, FALSE, now()) "
            "ON CONFLICT (name) DO UPDATE SET "
            "label = EXCLUDED.label, entity = EXCLUDED.entity, service = EXCLUDED.service, "
            "action = EXCLUDED.action, feature = EXCLUDED.feature"
        ).bindparams(
            name="agent:feedback",
            label="Submit Agent Feedback",
            entity="agent",
            service="agent-service",
            action="feedback",
            feature="agents",
        )
    )

    op.execute(
        sa.text("DELETE FROM permissions WHERE name IN :names").bindparams(
            sa.bindparam("names", value=REMOVED_PERMISSIONS, expanding=True)
        )
    )

    for table in ("roles", "composite_roles"):
        for permission in REMOVED_PERMISSIONS:
            op.execute(
                sa.text(
                    f"UPDATE {table} SET permissions = permissions - :permission "
                    "WHERE permissions ? :permission"
                ).bindparams(permission=permission)
            )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM permissions WHERE name = :name"
        ).bindparams(name="agent:feedback")
    )

    for table in ("roles", "composite_roles"):
        for permission in REMOVED_PERMISSIONS:
            op.execute(
                sa.text(
                    f"UPDATE {table} SET permissions = permissions || to_jsonb(:permission)"
                ).bindparams(permission=permission)
            )

    op.drop_column("permissions", "feature")
