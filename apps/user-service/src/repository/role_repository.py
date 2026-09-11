from typing import Any

from sqlalchemy import bindparam, delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.models import CompositeRoleModel

from .base_repository import BaseRepository


class CompositeRoleRepository(BaseRepository):
    @staticmethod
    async def _sync_normalized_access(
        session: AsyncSession,
        role_name: str,
        *,
        permissions: list[str] | None = None,
        role_ids: list[str] | None = None,
    ) -> None:
        if permissions is not None:
            await session.execute(
                text("DELETE FROM role_permissions WHERE role_name = :role_name"),
                {"role_name": role_name},
            )
            for permission in permissions:
                await session.execute(
                    text(
                        """
                        INSERT INTO role_permissions (role_name, permission_name)
                        VALUES (:role_name, :permission_name)
                        """
                    ),
                    {"role_name": role_name, "permission_name": permission},
                )

        if role_ids is not None:
            await session.execute(
                text("DELETE FROM role_hierarchy WHERE parent_role = :parent_role"),
                {"parent_role": role_name},
            )
            for child_role in role_ids:
                await session.execute(
                    text(
                        """
                        INSERT INTO role_hierarchy (parent_role, child_role)
                        VALUES (:parent_role, :child_role)
                        """
                    ),
                    {"parent_role": role_name, "child_role": child_role},
                )

    async def get_by_name(self, name: str) -> CompositeRoleModel | None:
        async with self._session() as session:
            result = await session.execute(
                select(CompositeRoleModel).where(CompositeRoleModel.name == name)
            )
            return result.scalar_one_or_none()

    async def get_all(self) -> list[CompositeRoleModel]:
        async with self._session() as session:
            result = await session.execute(
                select(CompositeRoleModel).order_by(CompositeRoleModel.name)
            )
            return list(result.scalars().all())

    async def get_by_names(self, names: list[str]) -> list[CompositeRoleModel]:
        if not names:
            return []
        async with self._session() as session:
            result = await session.execute(
                select(CompositeRoleModel).where(CompositeRoleModel.name.in_(names))
            )
            return list(result.scalars().all())

    async def get_access_by_names(self, names: list[str]) -> dict[str, dict[str, list[str]]]:
        if not names:
            return {}

        async with self._session() as session:
            role_result = await session.execute(
                text(
                    """
                    SELECT name
                    FROM composite_roles
                    WHERE name IN :names
                    """
                ).bindparams(bindparam("names", expanding=True)),
                {"names": names},
            )
            access: dict[str, dict[str, list[str]]] = {
                str(row[0]): {"permissions": [], "role_ids": []} for row in role_result.fetchall()
            }
            if not access:
                return {}

            existing_names = list(access)
            permission_result = await session.execute(
                text(
                    """
                    SELECT role_name, permission_name
                    FROM role_permissions
                    WHERE role_name IN :names
                    ORDER BY role_name, permission_name
                    """
                ).bindparams(bindparam("names", expanding=True)),
                {"names": existing_names},
            )
            for role_name, permission_name in permission_result.fetchall():
                access[str(role_name)]["permissions"].append(str(permission_name))

            hierarchy_result = await session.execute(
                text(
                    """
                    SELECT parent_role, child_role
                    FROM role_hierarchy
                    WHERE parent_role IN :names
                    ORDER BY parent_role, child_role
                    """
                ).bindparams(bindparam("names", expanding=True)),
                {"names": existing_names},
            )
            for parent_role, child_role in hierarchy_result.fetchall():
                access[str(parent_role)]["role_ids"].append(str(child_role))

            return access

    async def get_default_admin_role(self) -> CompositeRoleModel | None:
        # "system-admin" is the canonical full-access composite role (see
        # src.core.permissions.admin_roles) - resolve it by name rather than
        # a mutable per-row flag, so bootstrap always lands on the same role.
        return await self.get_by_name("system-admin")

    async def create(
        self,
        name: str,
        description: str | None = None,
        permissions: list[str] | None = None,
        role_ids: list[str] | None = None,
        is_builtin: bool = False,
    ) -> CompositeRoleModel:
        async with self._session() as session:
            role = CompositeRoleModel(
                name=name,
                description=description,
                permissions=permissions or [],
                role_ids=role_ids or [],
                is_builtin=is_builtin,
            )
            session.add(role)
            await session.flush()
            await self._sync_normalized_access(
                session,
                name,
                permissions=permissions or [],
                role_ids=role_ids or [],
            )
            await session.refresh(role)
            return role

    async def update(self, name: str, **updates: Any) -> CompositeRoleModel | None:
        async with self._session() as session:
            result = await session.execute(
                select(CompositeRoleModel).where(CompositeRoleModel.name == name)
            )
            role = result.scalar_one_or_none()
            if not role:
                return None
            for k, v in updates.items():
                if v is not None and hasattr(role, k):
                    setattr(role, k, v)
            await session.flush()
            await self._sync_normalized_access(
                session,
                name,
                permissions=updates.get("permissions"),
                role_ids=updates.get("role_ids"),
            )
            await session.refresh(role)
            return role

    async def delete(self, name: str) -> bool:
        async with self._session() as session:
            result = await session.execute(
                delete(CompositeRoleModel).where(CompositeRoleModel.name == name)
            )
            return result.rowcount > 0

    async def exists(self, name: str) -> bool:
        role = await self.get_by_name(name)
        return role is not None
