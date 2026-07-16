"""Repository for agent access groups."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update

from core.db.models.agent_group import AgentGroupModel
from core.db.repositories.base import BaseRepository


class AgentGroupRepository(BaseRepository):
    """CRUD operations for agent access groups."""

    @staticmethod
    def _to_dict(row: AgentGroupModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "user_ids": row.user_ids or [],
            "persona_ids": row.persona_ids or [],
            "created_by": row.created_by,
            "time_created": row.time_created.isoformat() if row.time_created else None,
            "time_updated": row.time_updated.isoformat() if row.time_updated else None,
        }

    async def list_all(self) -> list[dict[str, Any]]:
        async with self._session() as session:
            result = await session.execute(select(AgentGroupModel).order_by(AgentGroupModel.name))
            rows = result.scalars().all()
        return [self._to_dict(row) for row in rows]

    async def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """Return groups that explicitly include the given application user."""
        groups = await self.list_all()
        return [
            group
            for group in groups
            if user_id in {str(member_id) for member_id in group.get("user_ids", [])}
        ]

    async def get(self, group_id: int) -> dict[str, Any] | None:
        async with self._session() as session:
            result = await session.execute(
                select(AgentGroupModel).where(AgentGroupModel.id == group_id)
            )
            row = result.scalar_one_or_none()
        return self._to_dict(row) if row else None

    async def create(
        self,
        *,
        name: str,
        description: str = "",
        user_ids: list[str] | None = None,
        persona_ids: list[int] | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        async with self._session() as session:
            row = AgentGroupModel(
                name=name,
                description=description,
                user_ids=user_ids or [],
                persona_ids=persona_ids or [],
                created_by=created_by,
                time_created=now,
                time_updated=now,
            )
            session.add(row)
            await session.flush()
            return self._to_dict(row)

    async def update(self, group_id: int, **fields: Any) -> dict[str, Any] | None:
        allowed = {"name", "description", "user_ids", "persona_ids"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return await self.get(group_id)

        updates["time_updated"] = datetime.now(UTC)
        async with self._session() as session:
            await session.execute(
                update(AgentGroupModel).where(AgentGroupModel.id == group_id).values(**updates)
            )
        return await self.get(group_id)

    async def delete(self, group_id: int) -> bool:
        async with self._session() as session:
            result = await session.execute(
                delete(AgentGroupModel).where(AgentGroupModel.id == group_id)
            )
            return result.rowcount > 0
