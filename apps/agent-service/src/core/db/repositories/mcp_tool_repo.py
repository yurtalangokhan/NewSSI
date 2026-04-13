"""MCP Tool repository — typed CRUD for the ``mcp_tool`` table."""

from __future__ import annotations

import logging
import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.db.models.mcp_tool import MCPToolModel
from core.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class MCPToolRepository(BaseRepository):
    """CRUD operations on the ``mcp_tool`` table."""

    @staticmethod
    def _to_dict(row: MCPToolModel) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "provider_id": str(row.provider_id),
            "name": row.name,
            "description": row.description,
            "input_schema": row.input_schema or {},
            "output_schema": row.output_schema or {},
            "tool_metadata": row.tool_metadata or {},
            "category": row.category,
            "tags": row.tags or [],
            "is_active": row.is_active,
            "last_synced": row.last_synced.isoformat() if row.last_synced else None,
            "time_created": row.time_created.isoformat() if row.time_created else None,
        }

    async def list_all(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        async with self._session() as session:
            if include_inactive:
                stmt = select(MCPToolModel).order_by(MCPToolModel.name)
            else:
                stmt = (
                    select(MCPToolModel)
                    .where(MCPToolModel.is_active == True)
                    .order_by(MCPToolModel.name)
                )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    async def list_by_provider(
        self, provider_id: str, include_inactive: bool = False
    ) -> list[dict[str, Any]]:
        async with self._session() as session:
            if include_inactive:
                stmt = (
                    select(MCPToolModel)
                    .where(MCPToolModel.provider_id == provider_id)
                    .order_by(MCPToolModel.name)
                )
            else:
                stmt = (
                    select(MCPToolModel)
                    .where(
                        MCPToolModel.provider_id == provider_id,
                        MCPToolModel.is_active == True,
                    )
                    .order_by(MCPToolModel.name)
                )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    async def get_by_id(self, tool_id: str) -> dict[str, Any] | None:
        async with self._session() as session:
            stmt = select(MCPToolModel).where(MCPToolModel.id == tool_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def get_by_name(self, name: str, provider_id: str | None = None) -> dict[str, Any] | None:
        async with self._session() as session:
            if provider_id:
                stmt = select(MCPToolModel).where(
                    MCPToolModel.name == name, MCPToolModel.provider_id == provider_id
                )
            else:
                stmt = select(MCPToolModel).where(MCPToolModel.name == name)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def get_by_category(self, category: str) -> list[dict[str, Any]]:
        async with self._session() as session:
            stmt = (
                select(MCPToolModel)
                .where(
                    MCPToolModel.category == category,
                    MCPToolModel.is_active == True,
                )
                .order_by(MCPToolModel.name)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    async def list_categories(self) -> list[str]:
        async with self._session() as session:
            stmt = select(MCPToolModel.category).where(MCPToolModel.is_active == True).distinct()
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [c for c in rows if c]

    async def create(
        self,
        provider_id: str,
        name: str,
        description: str = "",
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        tool_metadata: dict[str, Any] | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        async with self._session() as session:
            stmt = (
                pg_insert(MCPToolModel)
                .values(
                    id=_uuid.uuid4(),
                    provider_id=provider_id,
                    name=name,
                    description=description,
                    input_schema=input_schema or {},
                    output_schema=output_schema or {},
                    tool_metadata=tool_metadata or {},
                    category=category,
                    tags=tags or [],
                    last_synced=datetime.now(UTC),
                )
                .returning(MCPToolModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one()
        return self._to_dict(row)

    async def upsert(
        self,
        provider_id: str,
        name: str,
        description: str = "",
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        tool_metadata: dict[str, Any] | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        async with self._session() as session:
            stmt = (
                pg_insert(MCPToolModel)
                .values(
                    id=_uuid.uuid4(),
                    provider_id=provider_id,
                    name=name,
                    description=description,
                    input_schema=input_schema or {},
                    output_schema=output_schema or {},
                    tool_metadata=tool_metadata or {},
                    category=category,
                    tags=tags or [],
                    last_synced=now,
                )
                .on_conflict_do_update(
                    index_elements=["provider_id", "name"],
                    set_={
                        "description": description,
                        "input_schema": input_schema or {},
                        "output_schema": output_schema or {},
                        "tool_metadata": tool_metadata or {},
                        "category": category,
                        "tags": tags or [],
                        "last_synced": now,
                    },
                )
                .returning(MCPToolModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one()
        return self._to_dict(row)

    async def bulk_upsert(self, provider_id: str, tools: list[dict[str, Any]]) -> int:
        now = datetime.now(UTC)
        inserted = 0
        async with self._session() as session:
            for tool in tools:
                stmt = (
                    pg_insert(MCPToolModel)
                    .values(
                        id=_uuid.uuid4(),
                        provider_id=provider_id,
                        name=tool.get("name", ""),
                        description=tool.get("description", ""),
                        input_schema=tool.get("input_schema", {}),
                        output_schema=tool.get("output_schema", {}),
                        tool_metadata=tool.get("tool_metadata", {}),
                        category=tool.get("category"),
                        tags=tool.get("tags", []),
                        last_synced=now,
                    )
                    .on_conflict_do_update(
                        index_elements=["provider_id", "name"],
                        set_={
                            "description": tool.get("description", ""),
                            "input_schema": tool.get("input_schema", {}),
                            "tool_metadata": tool.get("tool_metadata", {}),
                            "last_synced": now,
                        },
                    )
                    .returning(MCPToolModel)
                )
                try:
                    result = await session.execute(stmt)
                    if result.scalar_one_or_none():
                        inserted += 1
                except Exception as e:
                    logger.warning(f"Failed to upsert tool {tool.get('name')}: {e}")
        return inserted

    async def delete(self, tool_id: str) -> bool:
        async with self._session() as session:
            stmt = delete(MCPToolModel).where(MCPToolModel.id == tool_id)
            result = await session.execute(stmt)
            return result.rowcount > 0

    async def delete_by_provider(self, provider_id: str) -> int:
        async with self._session() as session:
            stmt = delete(MCPToolModel).where(MCPToolModel.provider_id == provider_id)
            result = await session.execute(stmt)
            return result.rowcount

    async def deactivate(self, tool_id: str) -> bool:
        async with self._session() as session:
            stmt = update(MCPToolModel).where(MCPToolModel.id == tool_id).values(is_active=False)
            result = await session.execute(stmt)
            return result.rowcount > 0
