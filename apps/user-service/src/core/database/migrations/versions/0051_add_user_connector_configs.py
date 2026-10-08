"""add user_connector_configs table

Connector configurations used to live in Airbyte's own database. They are now
stored here, per user, with the whole configuration document sealed under
CONNECTOR_CONFIG_ENCRYPTION_KEY. agent-service keeps only the row id.

``user_id`` has no foreign key, like the other per-user tables since the
Keycloak identity cutover (0049).

Revision ID: 0051
Revises: 0050
Create Date: 2026-09-30

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "user_connector_configs"
_USER_INDEX = "ix_user_connector_configs_user_id"


def upgrade() -> None:
    inspector = inspect(op.get_bind())

    if not inspector.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("connector_name", sa.String(100), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("config_encrypted", sa.Text(), nullable=False),
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
        )

    indexes = {index["name"] for index in inspect(op.get_bind()).get_indexes(_TABLE)}
    if _USER_INDEX not in indexes:
        op.create_index(_USER_INDEX, _TABLE, ["user_id"])


def downgrade() -> None:
    op.drop_index(_USER_INDEX, table_name=_TABLE)
    op.drop_table(_TABLE)
