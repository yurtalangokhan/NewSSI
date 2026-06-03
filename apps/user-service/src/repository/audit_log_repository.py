import uuid

from sqlalchemy import select

from src.core.database.models import AuditLogModel

from .base_repository import BaseRepository


class AuditLogRepository(BaseRepository):
    async def create(
        self,
        action: str,
        resource: str,
        user_id: uuid.UUID | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLogModel:
        async with self._session() as session:
            log = AuditLogModel(
                action=action,
                resource=resource,
                user_id=user_id,
                details=details or {},
                ip_address=ip_address,
                user_agent=user_agent,
            )
            session.add(log)
            await session.flush()
            await session.refresh(log)
            return log

    async def list_by_user(
        self, user_id: uuid.UUID, limit: int = 100, offset: int = 0
    ) -> list[AuditLogModel]:
        async with self._session() as session:
            result = await session.execute(
                select(AuditLogModel)
                .where(AuditLogModel.user_id == user_id)
                .order_by(AuditLogModel.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def list_by_action(
        self, action: str, limit: int = 100, offset: int = 0
    ) -> list[AuditLogModel]:
        async with self._session() as session:
            result = await session.execute(
                select(AuditLogModel)
                .where(AuditLogModel.action == action)
                .order_by(AuditLogModel.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def list_recent(self, limit: int = 100, offset: int = 0) -> list[AuditLogModel]:
        async with self._session() as session:
            result = await session.execute(
                select(AuditLogModel)
                .order_by(AuditLogModel.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(result.scalars().all())
