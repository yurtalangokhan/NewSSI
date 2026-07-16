import uuid
from datetime import datetime

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.models import UserModel

from .base_repository import BaseRepository


class UserRepository(BaseRepository):
    _has_external_keycloak_user_column: bool | None = None

    async def create(self, **kwargs) -> UserModel:
        async with self._session() as session:
            user = UserModel(**kwargs)
            session.add(user)
            await session.flush()
            await session.refresh(user)
            return user

    async def get_by_id(self, user_id: uuid.UUID) -> UserModel | None:
        async with self._session() as session:
            result = await session.execute(select(UserModel).where(UserModel.id == user_id))
            return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> UserModel | None:
        async with self._session() as session:
            result = await session.execute(
                select(UserModel).where(func.lower(UserModel.email) == func.lower(email))
            )
            return result.scalar_one_or_none()

    async def get_by_keycloak_id(self, keycloak_id: str) -> UserModel | None:
        async with self._session() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.keycloak_id == keycloak_id)
            )
            return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> UserModel | None:
        async with self._session() as session:
            result = await session.execute(
                select(UserModel).where(func.lower(UserModel.username) == func.lower(username))
            )
            return result.scalar_one_or_none()

    async def update(self, user_id: uuid.UUID, **kwargs) -> UserModel | None:
        async with self._session() as session:
            result = await session.execute(select(UserModel).where(UserModel.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return None
            for key, value in kwargs.items():
                if value is not None and hasattr(user, key):
                    setattr(user, key, value)
            user.updated_at = datetime.utcnow()
            await session.flush()
            await session.refresh(user)
            return user

    async def delete(self, user_id: uuid.UUID) -> bool:
        async with self._session() as session:
            result = await session.execute(delete(UserModel).where(UserModel.id == user_id))
            return result.rowcount > 0

    async def list_paginated(
        self,
        skip: int = 0,
        limit: int = 20,
        query: str | None = None,
        role: str | None = None,
        roles: list[str] | None = None,
        is_active: bool | None = None,
        invited: bool | None = None,
        include_external_keycloak_users: bool = True,
    ) -> tuple[list[UserModel], int]:
        async with self._session() as session:
            stmt = select(UserModel)
            count_stmt = select(func.count(UserModel.id))

            if query:
                search = f"%{query.lower()}%"
                stmt = stmt.where(
                    or_(
                        func.lower(UserModel.email).like(search),
                        func.lower(UserModel.first_name).like(search),
                        func.lower(UserModel.last_name).like(search),
                        func.lower(UserModel.username).like(search),
                    )
                )
                count_stmt = count_stmt.where(
                    or_(
                        func.lower(UserModel.email).like(search),
                        func.lower(UserModel.first_name).like(search),
                        func.lower(UserModel.last_name).like(search),
                        func.lower(UserModel.username).like(search),
                    )
                )

            if role:
                stmt = stmt.where(UserModel.role == role)
                count_stmt = count_stmt.where(UserModel.role == role)

            if roles:
                stmt = stmt.where(UserModel.role.in_(roles))
                count_stmt = count_stmt.where(UserModel.role.in_(roles))

            if is_active is not None:
                stmt = stmt.where(UserModel.is_active == is_active)
                count_stmt = count_stmt.where(UserModel.is_active == is_active)

            if invited is not None:
                stmt = stmt.where(UserModel.invited == invited)
                count_stmt = count_stmt.where(UserModel.invited == invited)

            if (
                not include_external_keycloak_users
                and await self._external_keycloak_user_column_exists(session)
            ):
                stmt = stmt.where(UserModel.is_external_keycloak_user.is_(False))
                count_stmt = count_stmt.where(UserModel.is_external_keycloak_user.is_(False))
            elif not include_external_keycloak_users:
                stmt = stmt.where(UserModel.keycloak_id.is_(None))
                count_stmt = count_stmt.where(UserModel.keycloak_id.is_(None))

            count_result = await session.execute(count_stmt)
            total = count_result.scalar_one()

            stmt = stmt.order_by(UserModel.created_at.desc()).offset(skip).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all()), total

    async def get_all(self) -> list[UserModel]:
        async with self._session() as session:
            result = await session.execute(select(UserModel).order_by(UserModel.created_at.desc()))
            return list(result.scalars().all())

    async def list_by_role(self, role: str) -> list[UserModel]:
        async with self._session() as session:
            result = await session.execute(select(UserModel).where(UserModel.role == role))
            return list(result.scalars().all())

    async def exists_by_email(self, email: str) -> bool:
        async with self._session() as session:
            result = await session.execute(
                select(func.count(UserModel.id)).where(
                    func.lower(UserModel.email) == func.lower(email)
                )
            )
            return result.scalar_one() > 0

    async def exists_by_keycloak_id(self, keycloak_id: str) -> bool:
        async with self._session() as session:
            result = await session.execute(
                select(func.count(UserModel.id)).where(UserModel.keycloak_id == keycloak_id)
            )
            return result.scalar_one() > 0

    async def upsert_by_keycloak_id(self, keycloak_id: str, **kwargs) -> UserModel:
        async with self._session() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.keycloak_id == keycloak_id)
            )
            user = result.scalar_one_or_none()
            if not user and kwargs.get("email"):
                result = await session.execute(
                    select(UserModel).where(
                        func.lower(UserModel.email) == func.lower(str(kwargs["email"]))
                    )
                )
                user = result.scalar_one_or_none()
            if user:
                kwargs["keycloak_id"] = keycloak_id
                for key, value in kwargs.items():
                    if value is not None and hasattr(user, key):
                        setattr(user, key, value)
                user.updated_at = datetime.utcnow()
            else:
                kwargs["keycloak_id"] = keycloak_id
                user = UserModel(**kwargs)
                session.add(user)
            await session.flush()
            await session.refresh(user)
            return user

    async def _external_keycloak_user_column_exists(self, session: AsyncSession) -> bool:
        if self._has_external_keycloak_user_column is not None:
            return self._has_external_keycloak_user_column

        result = await session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'users'
                      AND column_name = 'is_external_keycloak_user'
                )
                """
            )
        )
        self._has_external_keycloak_user_column = bool(result.scalar_one())
        return self._has_external_keycloak_user_column
