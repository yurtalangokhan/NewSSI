from typing import Any

from sqlalchemy import delete, select

from src.core.database.models import RoleModel

from .base_repository import BaseRepository


class RoleRepository(BaseRepository):
    async def get_by_name(self, name: str) -> RoleModel | None:
        async with self._session() as session:
            result = await session.execute(select(RoleModel).where(RoleModel.name == name))
            return result.scalar_one_or_none()

    async def get_all(self, service_client: str | None = None) -> list[RoleModel]:
        async with self._session() as session:
            query = select(RoleModel).order_by(RoleModel.service_client, RoleModel.name)
            if service_client:
                query = query.where(RoleModel.service_client == service_client)
            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_by_names(self, names: list[str]) -> list[RoleModel]:
        async with self._session() as session:
            result = await session.execute(select(RoleModel).where(RoleModel.name.in_(names)))
            return list(result.scalars().all())

    async def create(
        self,
        name: str,
        service_client: str,
        description: str | None = None,
        permissions: list[str] | None = None,
    ) -> RoleModel:
        async with self._session() as session:
            role = RoleModel(
                name=name,
                service_client=service_client,
                description=description,
                permissions=permissions or [],
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

    async def list_service_clients(self) -> list[str]:
        async with self._session() as session:
            result = await session.execute(
                select(RoleModel.service_client).distinct().order_by(RoleModel.service_client)
            )
            return [row[0] for row in result]
