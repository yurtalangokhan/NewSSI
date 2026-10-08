from datetime import UTC, datetime
from typing import Any
import uuid

from sqlalchemy import delete, select, update

from src.core.database.models import UserConnectorConfigModel

from .base_repository import BaseRepository


class UserConnectorConfigRepository(BaseRepository):
    """Rows of ``user_connector_configs``. ``config_encrypted`` is ciphertext;
    encryption and decryption happen in the service layer."""

    async def list_by_user(self, user_id: uuid.UUID) -> list[UserConnectorConfigModel]:
        async with self._session() as session:
            stmt = (
                select(UserConnectorConfigModel)
                .where(UserConnectorConfigModel.user_id == user_id)
                .order_by(UserConnectorConfigModel.created_at.desc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get(
        self, config_id: uuid.UUID, user_id: uuid.UUID
    ) -> UserConnectorConfigModel | None:
        async with self._session() as session:
            stmt = select(UserConnectorConfigModel).where(
                UserConnectorConfigModel.id == config_id,
                UserConnectorConfigModel.user_id == user_id,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def create(
        self,
        user_id: uuid.UUID,
        connector_name: str,
        name: str,
        config_encrypted: str,
    ) -> UserConnectorConfigModel:
        async with self._session() as session:
            now = datetime.now(UTC)
            row = UserConnectorConfigModel(
                id=uuid.uuid4(),
                user_id=user_id,
                connector_name=connector_name,
                name=name,
                config_encrypted=config_encrypted,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return row

    async def update(
        self,
        config_id: uuid.UUID,
        user_id: uuid.UUID,
        **fields: Any,
    ) -> UserConnectorConfigModel | None:
        """Update ``name`` and/or ``config_encrypted``; other keys are ignored."""
        values = {
            key: value
            for key, value in fields.items()
            if key in {"name", "config_encrypted"} and value is not None
        }
        if not values:
            return await self.get(config_id, user_id)
        values["updated_at"] = datetime.now(UTC)
        async with self._session() as session:
            stmt = (
                update(UserConnectorConfigModel)
                .where(
                    UserConnectorConfigModel.id == config_id,
                    UserConnectorConfigModel.user_id == user_id,
                )
                .values(**values)
                .returning(UserConnectorConfigModel)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def delete(self, config_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        async with self._session() as session:
            stmt = delete(UserConnectorConfigModel).where(
                UserConnectorConfigModel.id == config_id,
                UserConnectorConfigModel.user_id == user_id,
            )
            result = await session.execute(stmt)
            return result.rowcount > 0
