"""External MCP server infrastructure: auth/oauth columns + credential tables.

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    provider_cols = _columns("mcp_provider")

    # --- mcp_provider: surrogate int id ---------------------------------------
    if "int_id" not in provider_cols:
        op.execute("CREATE SEQUENCE IF NOT EXISTS mcp_provider_int_id_seq START 1000")
        op.add_column("mcp_provider", sa.Column("int_id", sa.BigInteger(), nullable=True))
        op.execute(
            "ALTER TABLE mcp_provider ALTER COLUMN int_id "
            "SET DEFAULT nextval('mcp_provider_int_id_seq')"
        )
        op.execute(
            "UPDATE mcp_provider SET int_id = nextval('mcp_provider_int_id_seq') "
            "WHERE int_id IS NULL"
        )
        op.alter_column("mcp_provider", "int_id", nullable=False)
        op.create_unique_constraint("uq_mcp_provider_int_id", "mcp_provider", ["int_id"])

    # --- mcp_provider: auth config columns ----------------------------------
    if "auth_type" not in provider_cols:
        op.add_column(
            "mcp_provider",
            sa.Column("auth_type", sa.String(20), nullable=False, server_default="NONE"),
        )
    if "auth_performer" not in provider_cols:
        op.add_column("mcp_provider", sa.Column("auth_performer", sa.String(20), nullable=True))
    if "server_status" not in provider_cols:
        op.add_column(
            "mcp_provider",
            sa.Column("server_status", sa.String(20), nullable=False, server_default="CREATED"),
        )
    if "auth_template" not in provider_cols:
        op.add_column("mcp_provider", sa.Column("auth_template", postgresql.JSONB(), nullable=True))
    if "owner_email" not in provider_cols:
        op.add_column("mcp_provider", sa.Column("owner_email", sa.String(320), nullable=True))
    if "oauth_metadata" not in provider_cols:
        op.add_column(
            "mcp_provider", sa.Column("oauth_metadata", postgresql.JSONB(), nullable=True)
        )

    op.execute("UPDATE mcp_provider SET server_status = 'CONNECTED' WHERE is_builtin = TRUE")

    # --- mcp_tool: surrogate int id + enabled -----------------------------
    tool_cols = _columns("mcp_tool")
    if "int_id" not in tool_cols:
        op.execute("CREATE SEQUENCE IF NOT EXISTS mcp_tool_int_id_seq START 1000")
        op.add_column("mcp_tool", sa.Column("int_id", sa.BigInteger(), nullable=True))
        op.execute(
            "ALTER TABLE mcp_tool ALTER COLUMN int_id SET DEFAULT nextval('mcp_tool_int_id_seq')"
        )
        op.execute(
            "UPDATE mcp_tool SET int_id = nextval('mcp_tool_int_id_seq') WHERE int_id IS NULL"
        )
        op.alter_column("mcp_tool", "int_id", nullable=False)
        op.create_unique_constraint("uq_mcp_tool_int_id", "mcp_tool", ["int_id"])
    if "enabled" not in tool_cols:
        op.add_column(
            "mcp_tool",
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        )

    # --- mcp_provider_auth --------------------------------------------------
    if not sa.inspect(op.get_bind()).has_table("mcp_provider_auth"):
        op.create_table(
            "mcp_provider_auth",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "provider_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("mcp_provider.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("user_id", sa.String(255), nullable=True),
            sa.Column("credentials_encrypted", sa.Text(), nullable=True),
            sa.Column("oauth_access_token_encrypted", sa.Text(), nullable=True),
            sa.Column("oauth_refresh_token_encrypted", sa.Text(), nullable=True),
            sa.Column("oauth_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("oauth_scopes", postgresql.JSONB(), nullable=True),
            sa.Column(
                "time_created",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "time_updated",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
        op.create_index("idx_mcp_provider_auth_provider_id", "mcp_provider_auth", ["provider_id"])
        op.execute(
            "CREATE UNIQUE INDEX uq_mcp_provider_auth_admin "
            "ON mcp_provider_auth (provider_id) WHERE user_id IS NULL"
        )
        op.execute(
            "CREATE UNIQUE INDEX uq_mcp_provider_auth_user "
            "ON mcp_provider_auth (provider_id, user_id) WHERE user_id IS NOT NULL"
        )

    # --- mcp_oauth_session -----------------------------------------------
    if not sa.inspect(op.get_bind()).has_table("mcp_oauth_session"):
        op.create_table(
            "mcp_oauth_session",
            sa.Column("state", sa.String(64), primary_key=True),
            sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", sa.String(255), nullable=False),
            sa.Column("code_verifier", sa.String(128), nullable=False),
            sa.Column("redirect_uri", sa.String(500), nullable=False),
            sa.Column("return_path", sa.String(500), nullable=True),
            sa.Column("client_id", sa.String(255), nullable=True),
            sa.Column("client_secret_encrypted", sa.Text(), nullable=True),
            sa.Column("token_url", sa.String(500), nullable=False),
            sa.Column("resource", sa.String(500), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "time_created",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
        op.create_index("idx_mcp_oauth_session_expires_at", "mcp_oauth_session", ["expires_at"])


def downgrade() -> None:
    op.drop_table("mcp_oauth_session")
    op.drop_table("mcp_provider_auth")

    op.drop_constraint("uq_mcp_tool_int_id", "mcp_tool", type_="unique")
    op.drop_column("mcp_tool", "enabled")
    op.drop_column("mcp_tool", "int_id")
    op.execute("DROP SEQUENCE IF EXISTS mcp_tool_int_id_seq")

    for col in (
        "oauth_metadata",
        "owner_email",
        "auth_template",
        "server_status",
        "auth_performer",
        "auth_type",
    ):
        op.drop_column("mcp_provider", col)
    op.drop_constraint("uq_mcp_provider_int_id", "mcp_provider", type_="unique")
    op.drop_column("mcp_provider", "int_id")
    op.execute("DROP SEQUENCE IF EXISTS mcp_provider_int_id_seq")
