from sqlalchemy import func, select

from src.core.database.models import PermissionModel

from .base_repository import BaseRepository


class PermissionRepository(BaseRepository):
    async def get_by_name(self, name: str) -> PermissionModel | None:
        async with self._session() as session:
            result = await session.execute(
                select(PermissionModel).where(PermissionModel.name == name)
            )
            return result.scalar_one_or_none()

    async def get_all(
        self,
        service: str | None = None,
        entity: str | None = None,
    ) -> list[PermissionModel]:
        async with self._session() as session:
            query = select(PermissionModel).order_by(
                PermissionModel.service, PermissionModel.entity, PermissionModel.name
            )
            if service:
                query = query.where(PermissionModel.service == service)
            if entity:
                query = query.where(PermissionModel.entity == entity)
            result = await session.execute(query)
            return list(result.scalars().all())

    async def list_entities(self) -> list[dict]:
        async with self._session() as session:
            result = await session.execute(
                select(
                    PermissionModel.service,
                    PermissionModel.entity,
                )
                .distinct()
                .order_by(PermissionModel.service, PermissionModel.entity)
            )
            seen = set()
            entities = []
            for service, entity in result:
                key = f"{service}:{entity}"
                if key not in seen:
                    seen.add(key)
                    entities.append(
                        {
                            "service": service,
                            "entity": entity,
                        }
                    )
            return entities

    async def count_by_service(self) -> list[dict]:
        async with self._session() as session:
            result = await session.execute(
                select(
                    PermissionModel.service,
                    func.count(PermissionModel.name).label("count"),
                )
                .group_by(PermissionModel.service)
                .order_by(PermissionModel.service)
            )
            return [{"service": row[0], "count": row[1]} for row in result]

    async def upsert_many(self, permissions: list[dict]) -> int:
        async with self._session() as session:
            for permission in permissions:
                await session.merge(PermissionModel(**permission))
            return len(permissions)
