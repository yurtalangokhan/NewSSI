"""Delete a thread's authored documents together with the thread.

0049 used ON DELETE SET NULL, which left every draft and revision of a deleted
chat behind with no route able to list it. Deleting a chat now deletes its
drafts (revisions already cascade from the document).

Revision ID: 0050
Revises: 0049
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK = "authored_documents_thread_id_fkey"


def _set_thread_fk(on_delete: str) -> None:
    op.execute(f"ALTER TABLE authored_documents DROP CONSTRAINT IF EXISTS {_FK}")
    op.execute(
        f"ALTER TABLE authored_documents ADD CONSTRAINT {_FK} "
        f"FOREIGN KEY (thread_id) REFERENCES thread(thread_id) ON DELETE {on_delete}"
    )


def upgrade() -> None:
    _set_thread_fk("CASCADE")


def downgrade() -> None:
    _set_thread_fk("SET NULL")
