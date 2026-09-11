"""Repository for end-user specific SMTP credentials."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from core.db.models.user_mail_credential import UserMailCredentialModel
from core.db.repositories.base import BaseRepository


class UserMailCredentialRepository(BaseRepository):
    """CRUD operations for the ``user_mail_credential`` table."""

    @staticmethod
    def _to_dict(row: UserMailCredentialModel) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "user_id": row.user_id,
            "mail_config_id": str(row.mail_config_id),
            "username": row.username,
            "password_encrypted": row.password_encrypted,
            "from_email": row.from_email,
            "from_name": row.from_name,
            "is_active": row.is_active,
            "last_tested_at": row.last_tested_at.isoformat() if row.last_tested_at else None,
            "time_created": row.time_created.isoformat() if row.time_created else None,
            "time_updated": row.time_updated.isoformat() if row.time_updated else None,
        }

    async def get_by_user_id(self, user_id: str) -> dict[str, Any] | None:
        async with self._session() as session:
            result = await session.execute(
                select(UserMailCredentialModel).where(
                    UserMailCredentialModel.user_id == user_id,
                    UserMailCredentialModel.is_active.is_(True),
                )
            )
            row = result.scalar_one_or_none()
        return self._to_dict(row) if row else None

    async def upsert(
        self,
        user_id: str,
        mail_config_id: str,
        username: str,
        password_encrypted: str,
        from_email: str,
        from_name: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        try:
            parsed_mail_config_id = UUID(mail_config_id)
        except ValueError as exc:
            raise ValueError("Invalid mail config ID") from exc
        async with self._session() as session:
            result = await session.execute(
                select(UserMailCredentialModel).where(UserMailCredentialModel.user_id == user_id)
            )
            row = result.scalar_one_or_none()
            if row:
                row.mail_config_id = parsed_mail_config_id
                row.username = username
                if password_encrypted:
                    row.password_encrypted = password_encrypted
                row.from_email = from_email
                row.from_name = from_name
                row.is_active = True
                row.time_updated = now
            else:
                row = UserMailCredentialModel(
                    user_id=user_id,
                    mail_config_id=parsed_mail_config_id,
                    username=username,
                    password_encrypted=password_encrypted,
                    from_email=from_email,
                    from_name=from_name,
                    is_active=True,
                    time_created=now,
                    time_updated=now,
                )
                session.add(row)
            await session.flush()
            await session.refresh(row)
            return self._to_dict(row)

    async def deactivate(self, user_id: str) -> bool:
        now = datetime.now(UTC)
        async with self._session() as session:
            result = await session.execute(
                select(UserMailCredentialModel).where(
                    UserMailCredentialModel.user_id == user_id,
                    UserMailCredentialModel.is_active.is_(True),
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                return False
            row.is_active = False
            row.time_updated = now
            return True

    async def mark_tested(self, user_id: str) -> bool:
        now = datetime.now(UTC)
        async with self._session() as session:
            result = await session.execute(
                select(UserMailCredentialModel).where(
                    UserMailCredentialModel.user_id == user_id,
                    UserMailCredentialModel.is_active.is_(True),
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                return False
            row.last_tested_at = now
            row.time_updated = now
            return True
