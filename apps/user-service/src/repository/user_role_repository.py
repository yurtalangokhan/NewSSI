import uuid

from sqlalchemy import delete, select, update

from src.core.database.models import UserRoleModel

from .base_repository import BaseRepository


class UserRoleRepository(BaseRepository):
    async def list_user_roles(self, user_id: uuid.UUID) -> list[dict[str, object]]:
        async with self._session() as session:
            result = await session.execute(
                select(UserRoleModel)
                .where(UserRoleModel.user_id == user_id)
                .order_by(UserRoleModel.is_primary.desc(), UserRoleModel.role_name)
            )
            return [
                {"name": role.role_name, "is_primary": role.is_primary}
                for role in result.scalars().all()
            ]

    async def list_user_ids_by_role(self, role_name: str) -> list[uuid.UUID]:
        async with self._session() as session:
            result = await session.execute(
                select(UserRoleModel.user_id).where(UserRoleModel.role_name == role_name)
            )
            return list(result.scalars().all())

    async def assign_roles(
        self,
        user_id: uuid.UUID,
        role_names: list[str],
        primary_role: str | None = None,
    ) -> None:
        async with self._session() as session:
            if primary_role is not None:
                await session.execute(
                    update(UserRoleModel)
                    .where(UserRoleModel.user_id == user_id)
                    .values(is_primary=False)
                )
            for role_name in role_names:
                is_primary = role_name == primary_role
                existing = await session.get(
                    UserRoleModel,
                    {"user_id": user_id, "role_name": role_name},
                )
                if existing:
                    if is_primary:
                        existing.is_primary = True
                    continue
                session.add(
                    UserRoleModel(
                        user_id=user_id,
                        role_name=role_name,
                        is_primary=is_primary,
                    )
                )

    async def replace_roles(
        self,
        user_id: uuid.UUID,
        role_names: list[str],
        primary_role: str | None = None,
    ) -> int:
        """Make `role_names` the user's COMPLETE set of role assignments.

        Unlike `assign_roles` (additive - it pairs with `remove_role` for the
        multi-role API), this revokes every assignment not in `role_names` and
        returns how many were revoked.

        Used by the single-role setter, where `users.role` and the Keycloak
        realm role are authoritative. Leaving a stale extra assignment behind
        keeps granting that role's permissions even though nothing in the UI
        shows it: a user demoted to "enduser" who silently kept a former
        "system-admin" assignment still resolves to full admin access, because
        permission resolution unions across every assigned role.
        """
        async with self._session() as session:
            if role_names:
                stale = delete(UserRoleModel).where(
                    UserRoleModel.user_id == user_id,
                    UserRoleModel.role_name.notin_(role_names),
                )
            else:
                stale = delete(UserRoleModel).where(UserRoleModel.user_id == user_id)
            revoked = (await session.execute(stale)).rowcount or 0

            for role_name in role_names:
                is_primary = role_name == primary_role
                existing = await session.get(
                    UserRoleModel,
                    {"user_id": user_id, "role_name": role_name},
                )
                if existing:
                    existing.is_primary = is_primary
                    continue
                session.add(
                    UserRoleModel(
                        user_id=user_id,
                        role_name=role_name,
                        is_primary=is_primary,
                    )
                )
            return revoked

    async def remove_role(self, user_id: uuid.UUID, role_name: str) -> bool:
        async with self._session() as session:
            result = await session.execute(
                delete(UserRoleModel).where(
                    UserRoleModel.user_id == user_id,
                    UserRoleModel.role_name == role_name,
                )
            )
            return result.rowcount > 0

    async def set_primary_role(self, user_id: uuid.UUID, role_name: str) -> bool:
        async with self._session() as session:
            existing = await session.get(
                UserRoleModel,
                {"user_id": user_id, "role_name": role_name},
            )
            if not existing:
                return False
            await session.execute(
                update(UserRoleModel)
                .where(UserRoleModel.user_id == user_id)
                .values(is_primary=False)
            )
            existing.is_primary = True
            return True
