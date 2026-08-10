"""Repository for resource permissions."""

import uuid
from typing import Any

from sqlalchemy import delete, func, select

from src.core.database.models import ResourcePermissionModel

from .base_repository import BaseRepository


class ResourcePermissionRepository(BaseRepository):
    """CRUD operations for resource permissions."""

    async def create(
        self,
        resource_type: str,
        resource_id: str,
        resource_name: str,
        organization_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        permission_level: str = "read",
        is_inherited: bool = False,
        granted_by: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Grant permission to organization or user."""
        if not organization_id and not user_id:
            raise ValueError("Either organization_id or user_id must be provided")
        if organization_id and user_id:
            raise ValueError("Only one of organization_id or user_id can be provided")

        async with self._session() as session:
            perm = ResourcePermissionModel(
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=resource_name,
                organization_id=organization_id,
                user_id=user_id,
                permission_level=permission_level,
                is_inherited=is_inherited,
                granted_by=granted_by,
            )
            session.add(perm)
            await session.flush()
            await session.refresh(perm)
            return self._to_dict(perm)

    async def get_by_id(self, permission_id: uuid.UUID) -> dict[str, Any] | None:
        """Get permission by ID."""
        async with self._session() as session:
            perm = await session.get(ResourcePermissionModel, permission_id)
            return self._to_dict(perm) if perm else None

    async def get_by_org_resource(
        self,
        organization_id: uuid.UUID,
        resource_type: str,
        resource_id: str,
    ) -> dict[str, Any] | None:
        """Get organization permission for resource."""
        async with self._session() as session:
            result = await session.execute(
                select(ResourcePermissionModel).where(
                    ResourcePermissionModel.organization_id == organization_id,
                    ResourcePermissionModel.resource_type == resource_type,
                    ResourcePermissionModel.resource_id == resource_id,
                )
            )
            perm = result.scalar_one_or_none()
            return self._to_dict(perm) if perm else None

    async def get_by_user_resource(
        self,
        user_id: uuid.UUID,
        resource_type: str,
        resource_id: str,
    ) -> dict[str, Any] | None:
        """Get user permission for resource."""
        async with self._session() as session:
            result = await session.execute(
                select(ResourcePermissionModel).where(
                    ResourcePermissionModel.user_id == user_id,
                    ResourcePermissionModel.resource_type == resource_type,
                    ResourcePermissionModel.resource_id == resource_id,
                )
            )
            perm = result.scalar_one_or_none()
            return self._to_dict(perm) if perm else None

    async def get_organization_permissions(
        self,
        organization_id: uuid.UUID,
        resource_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all permissions for an organization."""
        async with self._session() as session:
            query = select(ResourcePermissionModel).where(
                ResourcePermissionModel.organization_id == organization_id
            )

            if resource_type:
                query = query.where(ResourcePermissionModel.resource_type == resource_type)

            query = query.order_by(
                ResourcePermissionModel.resource_type,
                ResourcePermissionModel.resource_name,
            )
            result = await session.execute(query)
            return [self._to_dict(perm) for perm in result.scalars().all()]

    async def get_user_permissions(
        self,
        user_id: uuid.UUID,
        resource_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all direct permissions for a user."""
        async with self._session() as session:
            query = select(ResourcePermissionModel).where(
                ResourcePermissionModel.user_id == user_id
            )

            if resource_type:
                query = query.where(ResourcePermissionModel.resource_type == resource_type)

            query = query.order_by(
                ResourcePermissionModel.resource_type,
                ResourcePermissionModel.resource_name,
            )
            result = await session.execute(query)
            return [self._to_dict(perm) for perm in result.scalars().all()]

    async def get_direct_permissions(
        self,
        target_type: str,
        target_id: uuid.UUID,
        resource_type: str,
    ) -> list[dict[str, Any]]:
        """Get only direct permissions for one organization or user target."""
        if target_type not in {"organization", "user"}:
            raise ValueError("target_type must be 'organization' or 'user'")

        target_column = (
            ResourcePermissionModel.organization_id
            if target_type == "organization"
            else ResourcePermissionModel.user_id
        )
        async with self._session() as session:
            result = await session.execute(
                select(ResourcePermissionModel)
                .where(
                    target_column == target_id,
                    ResourcePermissionModel.resource_type == resource_type,
                    ResourcePermissionModel.is_inherited.is_(False),
                )
                .order_by(ResourcePermissionModel.resource_name)
            )
            return [self._to_dict(perm) for perm in result.scalars().all()]

    async def get_resource_permissions(
        self,
        resource_type: str,
        resource_id: str,
    ) -> list[dict[str, Any]]:
        """Get all permissions for a resource (organizations + users)."""
        async with self._session() as session:
            result = await session.execute(
                select(ResourcePermissionModel)
                .where(
                    ResourcePermissionModel.resource_type == resource_type,
                    ResourcePermissionModel.resource_id == resource_id,
                )
                .order_by(
                    ResourcePermissionModel.organization_id.desc(),  # Orgs first
                    ResourcePermissionModel.permission_level,
                )
            )
            return [self._to_dict(perm) for perm in result.scalars().all()]

    async def sync_direct_permissions(
        self,
        target_type: str,
        target_id: uuid.UUID,
        resource_type: str,
        desired_permissions: list[dict[str, Any]],
        granted_by: uuid.UUID,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Atomically replace direct permissions and return their mutation change set."""
        if target_type not in {"organization", "user"}:
            raise ValueError("target_type must be 'organization' or 'user'")
        target_column = (
            ResourcePermissionModel.organization_id
            if target_type == "organization"
            else ResourcePermissionModel.user_id
        )
        target_values = (
            {"organization_id": target_id, "user_id": None}
            if target_type == "organization"
            else {"organization_id": None, "user_id": target_id}
        )
        desired_by_id = {item["resource_id"]: item for item in desired_permissions}
        changes: list[dict[str, Any]] = []

        async with self._session() as session:
            result = await session.execute(
                select(ResourcePermissionModel).where(
                    target_column == target_id,
                    ResourcePermissionModel.resource_type == resource_type,
                    ResourcePermissionModel.is_inherited.is_(False),
                )
            )
            existing = {item.resource_id: item for item in result.scalars().all()}

            for resource_id, desired in desired_by_id.items():
                permission = existing.get(resource_id)
                if permission is None:
                    permission = ResourcePermissionModel(
                        resource_type=resource_type,
                        resource_id=resource_id,
                        resource_name=desired["resource_name"],
                        permission_level=desired["permission_level"],
                        is_inherited=False,
                        granted_by=granted_by,
                        **target_values,
                    )
                    session.add(permission)
                    changes.append(
                        {
                            "action": "grant",
                            "permission": permission,
                            "old_permission_level": None,
                        }
                    )
                else:
                    old_permission = self._to_dict(permission, include_relationships=False)
                    changed = (
                        permission.resource_name != desired["resource_name"]
                        or permission.permission_level != desired["permission_level"]
                    )
                    permission.resource_name = desired["resource_name"]
                    permission.permission_level = desired["permission_level"]
                    permission.granted_by = granted_by
                    if changed:
                        changes.append(
                            {
                                "action": "update",
                                "permission": permission,
                                "old_permission_level": old_permission["permission_level"],
                            }
                        )

            omitted_ids = set(existing) - set(desired_by_id)
            if omitted_ids:
                changes.extend(
                    {
                        "action": "revoke",
                        "permission": self._to_dict(
                            existing[resource_id], include_relationships=False
                        ),
                        "old_permission_level": existing[resource_id].permission_level,
                    }
                    for resource_id in omitted_ids
                )
                await session.execute(
                    delete(ResourcePermissionModel).where(
                        target_column == target_id,
                        ResourcePermissionModel.resource_type == resource_type,
                        ResourcePermissionModel.resource_id.in_(omitted_ids),
                        ResourcePermissionModel.is_inherited.is_(False),
                    )
                )

            await session.flush()
            for change in changes:
                if isinstance(change["permission"], ResourcePermissionModel):
                    change["permission"] = self._to_dict(
                        change["permission"], include_relationships=False
                    )
            final_result = await session.execute(
                select(ResourcePermissionModel)
                .where(
                    target_column == target_id,
                    ResourcePermissionModel.resource_type == resource_type,
                    ResourcePermissionModel.is_inherited.is_(False),
                )
                .order_by(ResourcePermissionModel.resource_name)
            )
            return [self._to_dict(item) for item in final_result.scalars().all()], changes

    async def update(self, permission_id: uuid.UUID, **updates: Any) -> dict[str, Any] | None:
        """Update permission."""
        async with self._session() as session:
            perm = await session.get(ResourcePermissionModel, permission_id)
            if not perm:
                return None

            for key, value in updates.items():
                if hasattr(perm, key):
                    setattr(perm, key, value)

            await session.flush()
            await session.refresh(perm)
            return self._to_dict(perm)

    async def delete(self, permission_id: uuid.UUID) -> bool:
        """Revoke permission."""
        async with self._session() as session:
            result = await session.execute(
                delete(ResourcePermissionModel).where(ResourcePermissionModel.id == permission_id)
            )
            return result.rowcount > 0

    async def delete_organization_permissions(
        self,
        organization_id: uuid.UUID,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> int:
        """Delete permissions for organization (optionally filtered by resource)."""
        async with self._session() as session:
            query = delete(ResourcePermissionModel).where(
                ResourcePermissionModel.organization_id == organization_id
            )

            if resource_type:
                query = query.where(ResourcePermissionModel.resource_type == resource_type)
            if resource_id:
                query = query.where(ResourcePermissionModel.resource_id == resource_id)

            result = await session.execute(query)
            return result.rowcount

    async def delete_user_permissions(
        self,
        user_id: uuid.UUID,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> int:
        """Delete permissions for user (optionally filtered by resource)."""
        async with self._session() as session:
            query = delete(ResourcePermissionModel).where(
                ResourcePermissionModel.user_id == user_id
            )

            if resource_type:
                query = query.where(ResourcePermissionModel.resource_type == resource_type)
            if resource_id:
                query = query.where(ResourcePermissionModel.resource_id == resource_id)

            result = await session.execute(query)
            return result.rowcount

    async def bulk_create(self, permissions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Bulk create permissions."""
        async with self._session() as session:
            perm_models = [ResourcePermissionModel(**perm_data) for perm_data in permissions]
            session.add_all(perm_models)
            await session.flush()
            for pm in perm_models:
                await session.refresh(pm)
            return [self._to_dict(pm) for pm in perm_models]

    async def count_resource_permissions(self, resource_type: str, resource_id: str) -> int:
        """Count permissions for a resource."""
        async with self._session() as session:
            result = await session.execute(
                select(func.count(ResourcePermissionModel.id)).where(
                    ResourcePermissionModel.resource_type == resource_type,
                    ResourcePermissionModel.resource_id == resource_id,
                )
            )
            return result.scalar_one()

    def _to_dict(
        self,
        perm: ResourcePermissionModel,
        *,
        include_relationships: bool = True,
    ) -> dict[str, Any]:
        """Convert model to dict."""
        return {
            "id": perm.id,
            "resource_type": perm.resource_type,
            "resource_id": perm.resource_id,
            "resource_name": perm.resource_name,
            "organization_id": perm.organization_id,
            "user_id": perm.user_id,
            "permission_level": perm.permission_level,
            "is_inherited": perm.is_inherited,
            "granted_by": perm.granted_by,
            "granted_at": perm.granted_at.isoformat() if perm.granted_at else None,
            "expires_at": perm.expires_at.isoformat() if perm.expires_at else None,
            # Include related data if loaded
            "organization": (
                self._org_to_dict(perm.organization)
                if include_relationships and perm.organization
                else None
            ),
            "user": (
                self._user_to_dict(perm.user)
                if include_relationships and perm.user
                else None
            ),
        }

    def _org_to_dict(self, org) -> dict[str, Any]:
        """Convert organization to dict."""
        if not org:
            return {}
        return {
            "id": org.id,
            "name": org.name,
            "code": org.code,
        }

    def _user_to_dict(self, user) -> dict[str, Any]:
        """Convert user to dict."""
        if not user:
            return {}
        return {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }
