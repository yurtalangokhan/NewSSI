"""Repository for organization operations."""

import uuid
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError

from src.core.database.models import OrganizationModel
from src.core.exceptions import ConflictError

from .base_repository import BaseRepository


class OrganizationRepository(BaseRepository):
    """CRUD and tree operations for organizations."""

    async def create(
        self,
        name: str,
        code: str,
        parent_id: uuid.UUID | None = None,
        description: str | None = None,
        created_by: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Create new organization with computed path and level."""
        try:
            async with self._session() as session:
                # Compute path and level
                if parent_id:
                    parent = await session.get(OrganizationModel, parent_id)
                    if not parent:
                        raise ValueError(f"Parent organization {parent_id} not found")
                    path = f"{parent.path}{parent_id}/"
                    level = parent.level + 1
                else:
                    path = "/"
                    level = 0

                org = OrganizationModel(
                    name=name,
                    code=code,
                    description=description,
                    parent_id=parent_id,
                    path=path,
                    level=level,
                    order_index=0,
                    is_active=True,
                    metadata_json=metadata or {},
                    created_by=created_by,
                )
                session.add(org)
                await session.flush()
                await session.refresh(org)
                return self._to_dict(org)
        except IntegrityError as error:
            if parent_id is None:
                raise ConflictError("A root organization already exists") from error
            raise

    async def get_by_id(self, org_id: uuid.UUID) -> dict[str, Any] | None:
        """Get organization by ID."""
        async with self._session() as session:
            org = await session.get(OrganizationModel, org_id)
            return self._to_dict(org) if org else None

    async def get_by_code(self, code: str) -> dict[str, Any] | None:
        """Get organization by unique code."""
        async with self._session() as session:
            result = await session.execute(
                select(OrganizationModel).where(OrganizationModel.code == code)
            )
            org = result.scalar_one_or_none()
            return self._to_dict(org) if org else None

    async def update(self, org_id: uuid.UUID, **updates: Any) -> dict[str, Any] | None:
        """Update organization fields."""
        async with self._session() as session:
            org = await session.get(OrganizationModel, org_id)
            if not org:
                return None

            for key, value in updates.items():
                if value is not None and hasattr(org, key):
                    setattr(org, key, value)

            await session.flush()
            await session.refresh(org)
            return self._to_dict(org)

    async def delete(self, org_id: uuid.UUID) -> bool:
        """Delete organization (cascade to children)."""
        async with self._session() as session:
            result = await session.execute(
                delete(OrganizationModel).where(OrganizationModel.id == org_id)
            )
            return result.rowcount > 0

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        is_active: bool | None = None,
        parent_id: uuid.UUID | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """List organizations with pagination."""
        async with self._session() as session:
            query = select(OrganizationModel)
            count_query = select(func.count(OrganizationModel.id))

            if is_active is not None:
                query = query.where(OrganizationModel.is_active == is_active)
                count_query = count_query.where(OrganizationModel.is_active == is_active)

            if parent_id is not None:
                query = query.where(OrganizationModel.parent_id == parent_id)
                count_query = count_query.where(OrganizationModel.parent_id == parent_id)

            count_result = await session.execute(count_query)
            total = count_result.scalar_one()

            query = query.order_by(OrganizationModel.level, OrganizationModel.order_index)
            query = query.offset(skip).limit(limit)

            result = await session.execute(query)
            orgs = result.scalars().all()

            return [self._to_dict(org) for org in orgs], total

    async def get_children(
        self, parent_id: uuid.UUID, direct_only: bool = True
    ) -> list[dict[str, Any]]:
        """Get child organizations."""
        async with self._session() as session:
            if direct_only:
                # Direct children only
                query = select(OrganizationModel).where(OrganizationModel.parent_id == parent_id)
            else:
                # All descendants using path
                parent = await session.get(OrganizationModel, parent_id)
                if not parent:
                    return []
                query = select(OrganizationModel).where(
                    OrganizationModel.path.like(f"{parent.path}{parent_id}/%")
                )

            query = query.order_by(OrganizationModel.level, OrganizationModel.order_index)
            result = await session.execute(query)
            return [self._to_dict(org) for org in result.scalars().all()]

    async def get_ancestors(self, org_id: uuid.UUID) -> list[dict[str, Any]]:
        """Get all ancestor organizations up to root."""
        async with self._session() as session:
            org = await session.get(OrganizationModel, org_id)
            if not org:
                return []

            # Parse path to get ancestor IDs
            path_parts = [p for p in org.path.split("/") if p]
            if not path_parts:
                return []

            ancestor_ids = [uuid.UUID(p) for p in path_parts]

            # Fetch ancestors
            result = await session.execute(
                select(OrganizationModel)
                .where(OrganizationModel.id.in_(ancestor_ids))
                .order_by(OrganizationModel.level)
            )
            return [self._to_dict(org) for org in result.scalars().all()]

    async def move_organization(
        self, org_id: uuid.UUID, new_parent_id: uuid.UUID | None
    ) -> dict[str, Any] | None:
        """
        Move organization to new parent.

        Updates path for the organization and all descendants.
        """
        async with self._session() as session:
            org = await session.get(OrganizationModel, org_id)
            if not org:
                return None

            # Compute new path and level
            if new_parent_id:
                parent = await session.get(OrganizationModel, new_parent_id)
                if not parent:
                    raise ValueError(f"Parent organization {new_parent_id} not found")

                # Check for circular reference
                if str(new_parent_id) in org.path:
                    raise ValueError("Cannot move organization to its own descendant")

                new_path = f"{parent.path}{new_parent_id}/"
                new_level = parent.level + 1
            else:
                new_path = "/"
                new_level = 0

            old_path = org.path
            old_level = org.level
            level_diff = new_level - old_level

            # Update organization
            org.parent_id = new_parent_id
            org.path = new_path
            org.level = new_level

            # Update all descendants' paths
            descendants_result = await session.execute(
                select(OrganizationModel).where(
                    OrganizationModel.path.like(f"{old_path}{org_id}/%")
                )
            )
            descendants = descendants_result.scalars().all()

            for descendant in descendants:
                # Replace old path prefix with new path
                descendant.path = descendant.path.replace(old_path, new_path, 1)
                descendant.level = descendant.level + level_diff

            await session.flush()
            await session.refresh(org)
            return self._to_dict(org)

    async def search(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        """Search organizations by name, code, or description."""
        async with self._session() as session:
            search = f"%{query.lower()}%"
            result = await session.execute(
                select(OrganizationModel)
                .where(
                    or_(
                        func.lower(OrganizationModel.name).like(search),
                        func.lower(OrganizationModel.code).like(search),
                        func.lower(OrganizationModel.description).like(search),
                    )
                )
                .order_by(OrganizationModel.name)
                .limit(max_results)
            )
            return [self._to_dict(org) for org in result.scalars().all()]

    async def get_tree(
        self, root_id: uuid.UUID | None = None, max_depth: int | None = None
    ) -> dict[str, Any]:
        """
        Get hierarchical tree structure.

        Returns nested dict with children.
        """
        async with self._session() as session:
            if root_id:
                root = await session.get(OrganizationModel, root_id)
                if not root:
                    raise ValueError(f"Root organization {root_id} not found")

                # Get all descendants
                query = select(OrganizationModel).where(
                    or_(
                        OrganizationModel.id == root_id,
                        OrganizationModel.path.like(f"{root.path}{root_id}/%"),
                    )
                )

                if max_depth is not None:
                    query = query.where(OrganizationModel.level <= root.level + max_depth)
            else:
                # Get all organizations
                query = select(OrganizationModel)
                if max_depth is not None:
                    query = query.where(OrganizationModel.level <= max_depth)

            query = query.order_by(OrganizationModel.level, OrganizationModel.order_index)
            result = await session.execute(query)
            all_orgs = result.scalars().all()

            # Build tree structure
            org_dict = {str(org.id): self._to_dict(org) for org in all_orgs}

            # Add children arrays
            for org_data in org_dict.values():
                org_data["children"] = []

            # Build parent-child relationships
            root_nodes = []
            for org_data in org_dict.values():
                if org_data["parent_id"]:
                    parent_id_str = str(org_data["parent_id"])
                    if parent_id_str in org_dict:
                        org_dict[parent_id_str]["children"].append(org_data)
                else:
                    root_nodes.append(org_data)

            # Return single root or list of roots
            if root_id:
                return org_dict.get(str(root_id), {})
            else:
                return {"roots": root_nodes}

    async def get_stats(self) -> dict[str, Any]:
        """
        Get organization statistics.

        Returns:
            - total_organizations: Total count of all organizations
            - total_users: Total count of users assigned to any organization
            - total_permissions: Total count of organization-specific permissions
            - organizations_by_depth: Count of organizations at each level
        """
        async with self._session() as session:
            # Total organizations
            total_orgs_result = await session.execute(select(func.count(OrganizationModel.id)))
            total_organizations = total_orgs_result.scalar_one()

            # Organizations by depth
            depth_result = await session.execute(
                select(OrganizationModel.level, func.count(OrganizationModel.id))
                .group_by(OrganizationModel.level)
                .order_by(OrganizationModel.level)
            )
            organizations_by_depth = dict(depth_result.all())

            # Total users - count from user_organizations table
            from src.core.database.models import UserOrganizationModel

            total_users_result = await session.execute(
                select(func.count(func.distinct(UserOrganizationModel.user_id)))
            )
            total_users = total_users_result.scalar_one()

            # Total permissions - placeholder (implement when permission model is ready)
            total_permissions = 0

            return {
                "total_organizations": total_organizations,
                "total_users": total_users,
                "total_permissions": total_permissions,
                "organizations_by_depth": organizations_by_depth,
            }

    def _to_dict(self, org: OrganizationModel) -> dict[str, Any]:
        """Convert model to dict."""
        return {
            "id": org.id,
            "name": org.name,
            "code": org.code,
            "description": org.description,
            "parent_id": org.parent_id,
            "path": org.path,
            "level": org.level,
            "order_index": org.order_index,
            "is_active": org.is_active,
            "metadata": org.metadata_json,
            "created_at": org.created_at.isoformat() if org.created_at else None,
            "updated_at": org.updated_at.isoformat() if org.updated_at else None,
            "created_by": org.created_by,
        }
