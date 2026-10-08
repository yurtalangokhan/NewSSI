"""ORM model for the ``datasource_connections`` table."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
import uuid as _uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.db.models.base import Base

if TYPE_CHECKING:
    from infrastructure.db.models.collection import PgCollection


class DatasourceConnectionModel(Base):
    """Binds a datasource to the connector that fills it.

    The connector configuration itself is not stored here: ``config_id`` points
    at the encrypted row user-service keeps for ``owner_user_id``. ``catalog``
    is the configured stream selection (connector-py ``ConfiguredCatalog``).
    """

    __tablename__ = "datasource_connections"

    datasource_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("langchain_pg_collection.uuid", ondelete="CASCADE"),
        primary_key=True,
    )
    connector_name: Mapped[str] = mapped_column(String, nullable=False)
    config_id: Mapped[_uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(String, nullable=False)
    catalog: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    update_graph_rag: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    # Back-reference
    datasource: Mapped[PgCollection | None] = relationship(
        "PgCollection",
        back_populates="connection",
    )

    def __repr__(self) -> str:
        return f"<DatasourceConnection datasource={self.datasource_id!s} connector={self.connector_name!r}>"
