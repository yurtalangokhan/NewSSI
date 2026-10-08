"""Grant flow:* permissions to the canonical composite roles' role_permissions rows.

Migration 0044 tried to grant flow:* to the feature bundles behind
system-admin and enduser by updating the ``roles`` table rows named
"agent-admin" / "agent-manager" / "agent-enduser" — but 0024 (which runs
*before* 0044 in the revision chain) had already renamed those exact rows
to "agent-workspace-admin" / "agent-workspace-manager" / "agent-workspace-
user". So 0044's three ``UPDATE roles ... WHERE name = 'agent-admin'``
(etc.) statements matched zero rows and silently no-op'd. It also wrote
enterprise-admin's grant onto ``composite_roles.permissions`` (JSONB) —
but PermissionResolverService.resolve_effective_access resolves a
composite role's access via CompositeRoleRepository.get_access_by_names(),
which reads the normalized ``role_permissions``/``role_hierarchy`` tables
exclusively (see repository/role_repository.py) and never looks at
``composite_roles.permissions``/``role_ids`` at all. Those JSONB columns
are vestigial for this repository. Whatever earlier mechanism populated
enterprise-admin's 6 flow:* rows in ``role_permissions`` (confirmed present
in the live DB) is not this migration's own JSONB writes -- those were
always inert.

Net effect before this migration (verified against ``role_permissions``,
the table actually read at runtime):
  - system-admin: no flow:* rows
  - enterprise-admin: full flow:* rows already present - unchanged here
  - enduser: no flow:* rows

This migration inserts directly into ``role_permissions`` (role_name,
permission_name), the table CompositeRoleRepository.get_access_by_names()
actually reads, instead of the unread JSONB columns.

Revision ID: 0048_flow_permissions
Revises: 0048
Create Date: 2026-09-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0048_flow_permissions"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ALL_FLOW_PERMS = [
    "flow:read",
    "flow:create",
    "flow:update",
    "flow:delete",
    "flow:publish",
    "flow:execute",
]
_ENDUSER_FLOW_PERMS = ["flow:read", "flow:execute"]


def _add_role_permissions(role_name: str, permissions: list[str]) -> None:
    for permission in permissions:
        op.execute(
            sa.text(
                """
                INSERT INTO role_permissions (role_name, permission_name)
                VALUES (:role_name, :permission)
                ON CONFLICT (role_name, permission_name) DO NOTHING
                """
            ).bindparams(role_name=role_name, permission=permission)
        )


def _remove_role_permissions(role_name: str, permissions: list[str]) -> None:
    for permission in permissions:
        op.execute(
            sa.text(
                """
                DELETE FROM role_permissions
                WHERE role_name = :role_name AND permission_name = :permission
                """
            ).bindparams(role_name=role_name, permission=permission)
        )


def upgrade() -> None:
    _add_role_permissions("system-admin", _ALL_FLOW_PERMS)
    _add_role_permissions("enterprise-admin", _ALL_FLOW_PERMS)
    _add_role_permissions("enduser", _ENDUSER_FLOW_PERMS)


def downgrade() -> None:
    _remove_role_permissions("enduser", _ENDUSER_FLOW_PERMS)
    _remove_role_permissions("system-admin", _ALL_FLOW_PERMS)
