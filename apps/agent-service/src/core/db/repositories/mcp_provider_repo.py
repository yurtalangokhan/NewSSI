"""MCP Provider repository — typed CRUD for the ``mcp_provider`` table."""

from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.db.models.mcp_provider import MCPProviderModel
from core.db.repositories.base import BaseRepository
from core.logger import get_logger

logger = get_logger(__name__)


class MCPProviderRepository(BaseRepository):
    """CRUD operations on the ``mcp_provider`` table."""

    @staticmethod
    def _to_dict(row: MCPProviderModel) -> dict[str, Any]:
        """Convert an ORM row to a JSON-friendly dict."""
        return {
            "id": str(row.id),
            "int_id": row.int_id,
            "name": row.name,
            "type": row.type,
            "url": row.url,
            "transport": row.transport,
            "config": row.config or {},
            "is_active": row.is_active,
            "is_builtin": row.is_builtin,
            "description": row.description,
            "auth_type": row.auth_type,
            "auth_performer": row.auth_performer,
            "server_status": row.server_status,
            "auth_template": row.auth_template,
            "owner_email": row.owner_email,
            "oauth_metadata": row.oauth_metadata,
            "time_created": row.time_created.isoformat() if row.time_created else None,
            "time_updated": row.time_updated.isoformat() if row.time_updated else None,
        }

    async def list_all(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        """Return all providers."""
        async with self._session() as session:
            if include_inactive:
                stmt = select(MCPProviderModel).order_by(MCPProviderModel.name)
            else:
                stmt = (
                    select(MCPProviderModel)
                    .where(MCPProviderModel.is_active.is_(True))
                    .order_by(MCPProviderModel.name)
                )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    async def get_by_id(self, provider_id: str) -> dict[str, Any] | None:
        """Fetch a provider by ID."""
        async with self._session() as session:
            stmt = select(MCPProviderModel).where(MCPProviderModel.id == provider_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def get_by_name(self, name: str) -> dict[str, Any] | None:
        """Fetch a provider by name."""
        async with self._session() as session:
            stmt = select(MCPProviderModel).where(MCPProviderModel.name == name)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def get_by_int_id(self, int_id: int) -> dict[str, Any] | None:
        """Fetch a provider by its surrogate integer id."""
        async with self._session() as session:
            stmt = select(MCPProviderModel).where(MCPProviderModel.int_id == int_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def set_status(self, provider_id: str, status: str) -> bool:
        """Update ``server_status`` on a provider. Returns True if a row changed."""
        async with self._session() as session:
            stmt = (
                update(MCPProviderModel)
                .where(MCPProviderModel.id == provider_id)
                .values(server_status=status, time_updated=datetime.now(UTC))
            )
            result = await session.execute(stmt)
            return result.rowcount > 0

    async def get_builtin(self) -> dict[str, Any] | None:
        """Get the builtin tool-service provider."""
        async with self._session() as session:
            stmt = select(MCPProviderModel).where(MCPProviderModel.is_builtin.is_(True))
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def create(
        self,
        name: str,
        type: str = "external",
        url: str | None = None,
        transport: str = "streamable_http",
        config: dict[str, Any] | None = None,
        is_builtin: bool = False,
        description: str = "",
        auth_type: str = "NONE",
        auth_performer: str | None = None,
        server_status: str = "CREATED",
        auth_template: dict[str, Any] | None = None,
        owner_email: str | None = None,
        oauth_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Insert a new provider and return it."""
        now = datetime.now(UTC)
        async with self._session() as session:
            stmt = (
                pg_insert(MCPProviderModel)
                .values(
                    id=_uuid.uuid4(),
                    name=name,
                    type=type,
                    url=url,
                    transport=transport,
                    config=config or {},
                    is_builtin=is_builtin,
                    description=description,
                    auth_type=auth_type,
                    auth_performer=auth_performer,
                    server_status=server_status,
                    auth_template=auth_template,
                    owner_email=owner_email,
                    oauth_metadata=oauth_metadata,
                    time_created=now,
                    time_updated=now,
                )
                .returning(MCPProviderModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one()
        return self._to_dict(row)

    async def update(
        self,
        provider_id: str,
        **fields: Any,
    ) -> dict[str, Any] | None:
        """Update fields on a provider."""
        allowed = {
            "name",
            "type",
            "url",
            "transport",
            "config",
            "is_active",
            "description",
            "auth_type",
            "auth_performer",
            "server_status",
            "auth_template",
            "owner_email",
            "oauth_metadata",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return await self.get_by_id(provider_id)

        updates["time_updated"] = datetime.now(UTC)

        async with self._session() as session:
            stmt = (
                update(MCPProviderModel)
                .where(MCPProviderModel.id == provider_id)
                .values(**updates)
                .returning(MCPProviderModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def delete(self, provider_id: str) -> bool:
        """Delete a provider. Returns True if removed."""
        async with self._session() as session:
            stmt = delete(MCPProviderModel).where(MCPProviderModel.id == provider_id)
            result = await session.execute(stmt)
            return result.rowcount > 0

    async def deactivate(self, provider_id: str) -> bool:
        """Deactivate a provider (soft delete)."""
        async with self._session() as session:
            stmt = (
                update(MCPProviderModel)
                .where(MCPProviderModel.id == provider_id)
                .values(is_active=False, time_updated=datetime.now(UTC))
            )
            result = await session.execute(stmt)
            return result.rowcount > 0
