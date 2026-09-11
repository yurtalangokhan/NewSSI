"""Add flow:* permission catalog and grant to relevant roles.

flow:publish and flow:execute are separately grantable from flow:update —
the separation-of-duties control from flow-canvas design spec section 8:
agent-manager can build/test a flow but not promote it to production
(no flow:publish), and cannot delete a flow-backed agent either
(no flow:delete).

IMPORTANT table-name note (verified against migration 0011, which is EASY
to get backwards): 0011 renamed the original "roles" table (composite
roles like enterprise-admin/enduser) to "composite_roles", and renamed the
original "coarse_roles" table (service-client roles like agent-admin/
agent-manager/agent-enduser) to "roles". So as of this migration:
  - composite_roles -> enterprise-admin, enduser
  - roles           -> agent-admin, agent-manager, agent-enduser, etc.
This migration follows 0012's additive JSONB idiom against BOTH tables'
``permissions`` column directly (not 0009's whole-list-rewrite idiom,
which would silently delete anything an operator granted since deploy —
roles are tenant-customizable per migration 0007).

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FLOW_PERMISSIONS = [
    {
        "name": "flow:read",
        "label": "Read Flows",
        "entity": "flow",
        "service": "agent-service",
        "action": "read",
    },
    {
        "name": "flow:create",
        "label": "Create Flows",
        "entity": "flow",
        "service": "agent-service",
        "action": "create",
    },
    {
        "name": "flow:update",
        "label": "Update Flows",
        "entity": "flow",
        "service": "agent-service",
        "action": "update",
    },
    {
        "name": "flow:delete",
        "label": "Delete Flows",
        "entity": "flow",
        "service": "agent-service",
        "action": "delete",
    },
    {
        "name": "flow:publish",
        "label": "Publish Flows",
        "entity": "flow",
        "service": "agent-service",
        "action": "publish",
    },
    {
        "name": "flow:execute",
        "label": "Execute Flow Playground Runs",
        "entity": "flow",
        "service": "agent-service",
        "action": "execute",
    },
]

_ALL_FLOW_PERMS = [p["name"] for p in FLOW_PERMISSIONS]

_AGENT_MANAGER_FLOW_PERMS = ["flow:read", "flow:create", "flow:update", "flow:execute"]
_AGENT_ENDUSER_FLOW_PERMS = ["flow:read"]


def _jsonb_add_permissions(table: str, role_name: str, permissions: list[str]) -> None:
    for permission in permissions:
        op.execute(
            sa.text(
                f"""
                UPDATE {table}
                SET permissions = (
                    SELECT jsonb_agg(DISTINCT value ORDER BY value)
                    FROM jsonb_array_elements_text(
                        permissions || jsonb_build_array(:permission)
                    ) AS elem(value)
                )
                WHERE name = :role_name
                """
            ).bindparams(role_name=role_name, permission=permission)
        )


def _jsonb_remove_permissions(table: str, role_name: str, permissions: list[str]) -> None:
    for permission in permissions:
        op.execute(
            sa.text(
                f"""
                UPDATE {table}
                SET permissions = COALESCE(
                    (
                        SELECT jsonb_agg(value ORDER BY value)
                        FROM jsonb_array_elements_text(permissions) AS elem(value)
                        WHERE value <> :permission
                    ),
                    '[]'::jsonb
                )
                WHERE name = :role_name
                """
            ).bindparams(role_name=role_name, permission=permission)
        )


def upgrade() -> None:
    conn = op.get_bind()

    existing = {row[0] for row in conn.execute(sa.text("SELECT name FROM permissions")).fetchall()}

    added = 0
    for perm in FLOW_PERMISSIONS:
        if perm["name"] in existing:
            continue
        conn.execute(
            sa.text(
                """INSERT INTO permissions (name, label, description, entity, service, action, is_system)
                    VALUES (:name, :label, :description, :entity, :service, :action, :is_system)"""
            ).bindparams(
                name=perm["name"],
                label=perm["label"],
                description=f"Allows {perm['action']} on {perm['entity']}",
                entity=perm["entity"],
                service=perm["service"],
                action=perm["action"],
                is_system=False,
            )
        )
        added += 1
    print(f"Migration 0044: added {added} new flow:* permissions")

    # enterprise-admin is a composite role — full grant
    _jsonb_add_permissions("composite_roles", "enterprise-admin", _ALL_FLOW_PERMS)

    # agent-* are coarse (service-client) roles in the "roles" table
    _jsonb_add_permissions("roles", "agent-admin", _ALL_FLOW_PERMS)
    _jsonb_add_permissions("roles", "agent-manager", _AGENT_MANAGER_FLOW_PERMS)
    _jsonb_add_permissions("roles", "agent-enduser", _AGENT_ENDUSER_FLOW_PERMS)


def downgrade() -> None:
    _jsonb_remove_permissions("roles", "agent-enduser", _AGENT_ENDUSER_FLOW_PERMS)
    _jsonb_remove_permissions("roles", "agent-manager", _AGENT_MANAGER_FLOW_PERMS)
    _jsonb_remove_permissions("roles", "agent-admin", _ALL_FLOW_PERMS)
    _jsonb_remove_permissions("composite_roles", "enterprise-admin", _ALL_FLOW_PERMS)

    conn = op.get_bind()
    for perm in FLOW_PERMISSIONS:
        conn.execute(
            sa.text("DELETE FROM permissions WHERE name = :name").bindparams(name=perm["name"])
        )
