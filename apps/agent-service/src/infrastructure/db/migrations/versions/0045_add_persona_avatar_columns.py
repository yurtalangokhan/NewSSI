"""Add uploaded_image_id + icon_name to persona — the avatar was never stored.

PersonaUpsertRequest has accepted both fields since the avatar picker
shipped, and the catalog serializer reads both back, but the table had no
columns for them: every logo the user picked was silently dropped on save.

Additive and nullable; existing rows keep the name-letter/default glyph
avatar they already render.

Revision ID: 0045
Revises: 0044
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE persona ADD COLUMN IF NOT EXISTS uploaded_image_id TEXT NULL")
    op.execute("ALTER TABLE persona ADD COLUMN IF NOT EXISTS icon_name TEXT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE persona DROP COLUMN IF EXISTS icon_name")
    op.execute("ALTER TABLE persona DROP COLUMN IF EXISTS uploaded_image_id")
