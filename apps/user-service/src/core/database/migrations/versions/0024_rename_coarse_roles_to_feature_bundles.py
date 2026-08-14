"""rename coarse roles to feature bundles

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ROLE_RENAMES: dict[str, tuple[str, str]] = {
    "user-admin": (
        "access-admin",
        "Full users and access management",
    ),
    "user-manager": (
        "access-manager",
        "Operational users and access management",
    ),
    "enduser": (
        "account-self-service",
        "Basic account self-service permissions for end users",
    ),
    "agent-admin": (
        "agent-workspace-admin",
        "Full agents and workspace management",
    ),
    "agent-manager": (
        "agent-workspace-manager",
        "Operational agents and workspace management",
    ),
    "agent-enduser": (
        "agent-workspace-user",
        "Agent, chat, project, and memory use",
    ),
    "rag-admin": (
        "knowledge-admin",
        "Full knowledge and RAG management",
    ),
    "rag-manager": (
        "knowledge-manager",
        "Operational knowledge management",
    ),
    "rag-enduser": (
        "knowledge-search-user",
        "Knowledge search and read access",
    ),
    "tool-admin": (
        "tooling-admin",
        "Full tools and integration management",
    ),
    "tool-user": (
        "tooling-user",
        "Tool execution and catalog access",
    ),
}


def _merge_or_rename_role(old_name: str, new_name: str, description: str) -> None:
    op.execute(
        sa.text(
            """
            UPDATE roles AS target
            SET permissions = COALESCE(
                    (
                        SELECT jsonb_agg(DISTINCT value ORDER BY value)
                        FROM jsonb_array_elements_text(
                            target.permissions || source.permissions
                        ) AS elem(value)
                    ),
                    '[]'::jsonb
                ),
                description = COALESCE(target.description, :description)
            FROM roles AS source
            WHERE target.name = :new_name
              AND source.name = :old_name
            """
        ).bindparams(old_name=old_name, new_name=new_name, description=description)
    )
    op.execute(
        sa.text(
            """
            DELETE FROM roles
            WHERE name = :old_name
              AND EXISTS (SELECT 1 FROM roles WHERE name = :new_name)
            """
        ).bindparams(old_name=old_name, new_name=new_name)
    )
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET name = :new_name,
                description = :description
            WHERE name = :old_name
            """
        ).bindparams(old_name=old_name, new_name=new_name, description=description)
    )


def _replace_role_id(old_name: str, new_name: str) -> None:
    op.execute(
        sa.text(
            """
            UPDATE composite_roles
            SET role_ids = COALESCE(
                (
                    SELECT jsonb_agg(DISTINCT replacement ORDER BY replacement)
                    FROM (
                        SELECT CASE value
                            WHEN :old_name THEN :new_name
                            ELSE value
                        END AS replacement
                        FROM jsonb_array_elements_text(role_ids) AS elem(value)
                    ) AS replacements
                ),
                '[]'::jsonb
            )
            WHERE role_ids ? :old_name
            """
        ).bindparams(old_name=old_name, new_name=new_name)
    )


def upgrade() -> None:
    for old_name, (new_name, description) in ROLE_RENAMES.items():
        _merge_or_rename_role(old_name, new_name, description)
        _replace_role_id(old_name, new_name)
    op.execute(
        """
        UPDATE composite_roles
        SET permissions = '[]'::jsonb
        WHERE name IN ('system-admin', 'enterprise-admin', 'enduser')
        """
    )


def downgrade() -> None:
    for old_name, (new_name, _description) in reversed(ROLE_RENAMES.items()):
        _merge_or_rename_role(new_name, old_name, old_name)
        _replace_role_id(new_name, old_name)
