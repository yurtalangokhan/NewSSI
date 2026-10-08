"""ORM model for the ``knowledge_evidence`` table.

One row per knowledge retrieval call (a ``database_search``/``graph_search``
tool call or a flow retrieval node run): the chunks and subgraph the model was
given, kept so the chat can show them again after a reload. Rows live and die
with their thread. The checkpoint and flow timeline hold only the row id — the
payload stays out of them because the checkpoint rewrites the whole message
list on every step.
"""

from __future__ import annotations

from datetime import datetime
import uuid as _uuid

from sqlalchemy import DateTime, ForeignKey, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.models.base import Base


class KnowledgeEvidenceModel(Base):
    """A persisted ``KnowledgeEvidence`` payload, scoped to one thread."""

    __tablename__ = "knowledge_evidence"

    id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=_uuid.uuid4,
    )
    thread_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("thread.thread_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
