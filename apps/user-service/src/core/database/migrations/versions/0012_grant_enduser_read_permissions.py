"""grant enduser read permissions needed by app flows

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ENDUSER_DIRECT_PERMISSIONS = [
    "datasource:read",
    "document:read",
    "graph:read",
    "mcp_provider:read",
]

RAG_ENDUSER_PERMISSIONS = [
    "datasource:read",
    "document:read",
    "graph:read",
]

TOOL_USER_PERMISSIONS = [
    "mcp_provider:read",
]


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
    _jsonb_add_permissions("composite_roles", "enduser", ENDUSER_DIRECT_PERMISSIONS)
    _jsonb_add_permissions("roles", "rag-enduser", RAG_ENDUSER_PERMISSIONS)
    _jsonb_add_permissions("roles", "tool-user", TOOL_USER_PERMISSIONS)


def downgrade() -> None:
    _jsonb_remove_permissions("roles", "tool-user", TOOL_USER_PERMISSIONS)
    _jsonb_remove_permissions("roles", "rag-enduser", RAG_ENDUSER_PERMISSIONS)
    _jsonb_remove_permissions("composite_roles", "enduser", ENDUSER_DIRECT_PERMISSIONS)
