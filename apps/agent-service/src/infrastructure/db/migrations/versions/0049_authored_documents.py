"""Add authored_documents + authored_document_revisions (document drafts).

Additive. The existing `document` table stays the rendered-file store; a
revision points at its render via `rendered_file_id`. See
.tmp/document-drafts/design.md section 4.1.

Revision ID: 0049
Revises: 0048
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS authored_documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL,
            thread_id UUID REFERENCES thread(thread_id) ON DELETE SET NULL,
            project_id INTEGER REFERENCES project(id) ON DELETE SET NULL,
            kind VARCHAR(20) NOT NULL,
            title TEXT,
            filename TEXT NOT NULL,
            format VARCHAR(10) NOT NULL,
            head_revision_no INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_authored_documents_user_id ON authored_documents (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_authored_documents_thread_id ON authored_documents (thread_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS authored_document_revisions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id UUID NOT NULL REFERENCES authored_documents(id) ON DELETE CASCADE,
            revision_no INTEGER NOT NULL,
            parent_revision_id UUID,
            restored_from_revision_id UUID,
            source_format VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            options JSONB NOT NULL DEFAULT '{}'::jsonb,
            title TEXT,
            filename TEXT NOT NULL,
            format VARCHAR(10) NOT NULL,
            content_sha256 VARCHAR(64) NOT NULL,
            operation VARCHAR(20) NOT NULL,
            author_type VARCHAR(10) NOT NULL,
            author_id TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            edit_ops JSONB,
            stats JSONB NOT NULL DEFAULT '{}'::jsonb,
            rendered_file_id VARCHAR(64),
            tool_call_id TEXT,
            run_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_authored_document_revisions_doc_no UNIQUE (document_id, revision_no)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_authored_document_revisions_document_id "
        "ON authored_document_revisions (document_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_authored_document_revisions_rendered_file_id "
        "ON authored_document_revisions (rendered_file_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS authored_document_revisions")
    op.execute("DROP TABLE IF EXISTS authored_documents")
