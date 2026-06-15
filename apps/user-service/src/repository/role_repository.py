from typing import Any

from sqlalchemy import delete, select

from src.core.database.models import RoleModel

from .base_repository import BaseRepository


class RoleRepository(BaseRepository):
    SUPPORTED_ROLES = ["admin", "enduser"]

    async def get_by_name(self, name: str) -> RoleModel | None:
        async with self._session() as session:
            result = await session.execute(select(RoleModel).where(RoleModel.name == name))
            return result.scalar_one_or_none()

    async def get_all(self) -> list[RoleModel]:
        async with self._session() as session:
            result = await session.execute(select(RoleModel).order_by(RoleModel.name))
            return list(result.scalars().all())

    async def create(
        self,
        name: str,
        description: str | None = None,
        permissions: list[str] | None = None,
        is_builtin: bool = False,
    ) -> RoleModel:
        async with self._session() as session:
            role = RoleModel(
                name=name,
                description=description,
                permissions=permissions or [],
                is_builtin=is_builtin,
            )
            session.add(role)
            await session.flush()
            await session.refresh(role)
            return role

    async def update(self, name: str, **updates: Any) -> RoleModel | None:
        async with self._session() as session:
            result = await session.execute(select(RoleModel).where(RoleModel.name == name))
            role = result.scalar_one_or_none()
            if not role:
                return None
            for k, v in updates.items():
                if v is not None and hasattr(role, k):
                    setattr(role, k, v)
            await session.flush()
            await session.refresh(role)
            return role

    async def delete(self, name: str) -> bool:
        async with self._session() as session:
            result = await session.execute(delete(RoleModel).where(RoleModel.name == name))
            return result.rowcount > 0

    async def exists(self, name: str) -> bool:
        role = await self.get_by_name(name)
        return role is not None
