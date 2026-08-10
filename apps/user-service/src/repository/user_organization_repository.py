"""Repository for user-organization relationships."""

import uuid
from typing import Any

from sqlalchemy import delete, func, select

from src.core.database.models import (
    ResourcePermissionModel,
    UserModel,
    UserOrganizationModel,
)

from .base_repository import BaseRepository


class UserOrganizationRepository(BaseRepository):
    """CRUD operations for user-organization assignments."""

    async def create(
        self,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        role_in_org: str = "member",
        is_primary: bool = False,
        assigned_by: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Assign user to organization."""
        async with self._session() as session:
            user_org = UserOrganizationModel(
                user_id=user_id,
                organization_id=organization_id,
                role_in_org=role_in_org,
                is_primary=is_primary,
                is_active=True,
                assigned_by=assigned_by,
            )
            session.add(user_org)
            await session.flush()
            await session.refresh(user_org)
            return self._to_dict(user_org)

    async def get_by_id(self, user_org_id: uuid.UUID) -> dict[str, Any] | None:
        """Get user-organization relationship by ID."""
        async with self._session() as session:
            user_org = await session.get(UserOrganizationModel, user_org_id)
            return self._to_dict(user_org) if user_org else None

    async def get_by_user_and_org(
        self, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """Get user-organization relationship."""
        async with self._session() as session:
            result = await session.execute(
                select(UserOrganizationModel).where(
                    UserOrganizationModel.user_id == user_id,
                    UserOrganizationModel.organization_id == organization_id,
                )
            )
            user_org = result.scalar_one_or_none()
            return self._to_dict(user_org) if user_org else None

    async def get_user_organizations(
        self, user_id: uuid.UUID, include_inactive: bool = False
    ) -> list[dict[str, Any]]:
        """Get all organizations for a user."""
        async with self._session() as session:
            query = select(UserOrganizationModel).where(UserOrganizationModel.user_id == user_id)
            if not include_inactive:
                query = query.where(UserOrganizationModel.is_active)

            query = query.order_by(
                UserOrganizationModel.is_primary.desc(),
                UserOrganizationModel.joined_at.desc(),
            )
            result = await session.execute(query)
            return [self._to_dict(uo) for uo in result.scalars().all()]

    async def get_active_unit_manager_organizations(
        self, user_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Return active organization memberships where the user is a unit manager."""
        async with self._session() as session:
            result = await session.execute(
                select(UserOrganizationModel).where(
                    UserOrganizationModel.user_id == user_id,
                    UserOrganizationModel.role_in_org == "unit_manager",
                    UserOrganizationModel.is_active,
                )
            )
            return [self._to_dict(user_org) for user_org in result.scalars().all()]

    async def get_organization_users(
        self,
        organization_id: uuid.UUID,
        role_in_org: str | None = None,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        """Get all users in an organization."""
        async with self._session() as session:
            query = select(UserOrganizationModel).where(
                UserOrganizationModel.organization_id == organization_id
            )

            if role_in_org:
                query = query.where(UserOrganizationModel.role_in_org == role_in_org)

            if not include_inactive:
                query = query.where(UserOrganizationModel.is_active)

            query = query.order_by(
                UserOrganizationModel.role_in_org,
                UserOrganizationModel.joined_at,
            )
            result = await session.execute(query)
            return [self._to_dict(uo) for uo in result.scalars().all()]

    async def update(self, user_org_id: uuid.UUID, **updates: Any) -> dict[str, Any] | None:
        """Update user-organization relationship."""
        async with self._session() as session:
            user_org = await session.get(UserOrganizationModel, user_org_id)
            if not user_org:
                return None

            for key, value in updates.items():
                if hasattr(user_org, key):
                    setattr(user_org, key, value)

            await session.flush()
            await session.refresh(user_org)
            return self._to_dict(user_org)

    async def delete(self, user_id: uuid.UUID, organization_id: uuid.UUID) -> bool:
        """Remove user from organization."""
        async with self._session() as session:
            result = await session.execute(
                delete(UserOrganizationModel).where(
                    UserOrganizationModel.user_id == user_id,
                    UserOrganizationModel.organization_id == organization_id,
                )
            )
            return result.rowcount > 0

    async def delete_and_cleanup_orphan_permissions(
        self, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> tuple[bool, int]:
        """Remove membership and delete user grants only after the final membership."""
        async with self._session() as session:
            # Serialize concurrent membership removals for the same user so two
            # transactions cannot both observe another membership and leave
            # orphaned permissions behind.
            await session.execute(
                select(UserModel.id).where(UserModel.id == user_id).with_for_update()
            )
            membership_result = await session.execute(
                delete(UserOrganizationModel).where(
                    UserOrganizationModel.user_id == user_id,
                    UserOrganizationModel.organization_id == organization_id,
                )
            )
            if membership_result.rowcount == 0:
                return False, 0

            remaining_result = await session.execute(
                select(func.count(UserOrganizationModel.id)).where(
                    UserOrganizationModel.user_id == user_id,
                    UserOrganizationModel.is_active,
                )
            )
            if remaining_result.scalar_one() > 0:
                return True, 0

            permission_result = await session.execute(
                delete(ResourcePermissionModel).where(ResourcePermissionModel.user_id == user_id)
            )
            return True, permission_result.rowcount

    async def set_primary(
        self, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """Set organization as primary for user."""
        async with self._session() as session:
            # Unset all primary flags for this user
            await session.execute(
                select(UserOrganizationModel)
                .where(UserOrganizationModel.user_id == user_id)
                .execution_options(synchronize_session="fetch")
            )

            result = await session.execute(
                select(UserOrganizationModel).where(UserOrganizationModel.user_id == user_id)
            )
            user_orgs = result.scalars().all()
            for uo in user_orgs:
                uo.is_primary = False

            # Set new primary
            target_result = await session.execute(
                select(UserOrganizationModel).where(
                    UserOrganizationModel.user_id == user_id,
                    UserOrganizationModel.organization_id == organization_id,
                )
            )
            target = target_result.scalar_one_or_none()
            if not target:
                return None

            target.is_primary = True
            await session.flush()
            await session.refresh(target)
            return self._to_dict(target)

    async def get_primary_organization(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        """Get user's primary organization."""
        async with self._session() as session:
            result = await session.execute(
                select(UserOrganizationModel).where(
                    UserOrganizationModel.user_id == user_id,
                    UserOrganizationModel.is_primary,
                    UserOrganizationModel.is_active,
                )
            )
            user_org = result.scalar_one_or_none()
            return self._to_dict(user_org) if user_org else None

    async def count_organization_users(self, organization_id: uuid.UUID) -> int:
        """Count active users in organization."""
        async with self._session() as session:
            result = await session.execute(
                select(func.count(UserOrganizationModel.id)).where(
                    UserOrganizationModel.organization_id == organization_id,
                    UserOrganizationModel.is_active,
                )
            )
            return result.scalar_one()

    def _to_dict(self, user_org: UserOrganizationModel) -> dict[str, Any]:
        """Convert model to dict."""
        return {
            "id": user_org.id,
            "user_id": user_org.user_id,
            "organization_id": user_org.organization_id,
            "role_in_org": user_org.role_in_org,
            "is_primary": user_org.is_primary,
            "is_active": user_org.is_active,
            "joined_at": user_org.joined_at.isoformat() if user_org.joined_at else None,
            "assigned_by": user_org.assigned_by,
            # Include related data if loaded
            "user": self._user_to_dict(user_org.user) if user_org.user else None,
            "organization": (
                self._org_to_dict(user_org.organization) if user_org.organization else None
            ),
        }

    def _user_to_dict(self, user) -> dict[str, Any]:
        """Convert user model to dict."""
        if not user:
            return {}
        return {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
        }

    def _org_to_dict(self, org) -> dict[str, Any]:
        """Convert organization model to dict."""
        if not org:
            return {}
        return {
            "id": org.id,
            "name": org.name,
            "code": org.code,
            "level": org.level,
        }
