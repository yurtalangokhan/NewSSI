"""Organization management service."""

import uuid
from typing import Any

from src.core.exceptions import ConflictError
from src.repository import OrganizationRepository


class OrganizationService:
    """Business logic for organization hierarchy management."""

    def __init__(self):
        self.repo = OrganizationRepository()

    async def create_organization(
        self,
        name: str,
        code: str,
        parent_id: uuid.UUID | None = None,
        description: str | None = None,
        created_by: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Create new organization with validation."""
        # Check for duplicate code
        existing = await self.repo.get_by_code(code)
        if existing:
            raise ValueError(f"Organization with code '{code}' already exists")

        # The enterprise hierarchy has exactly one root.  Any existing
        # organization implies the root has already been established.
        if parent_id is None:
            _organizations, total = await self.repo.list_all(skip=0, limit=1)
            if total:
                raise ValueError("A root organization already exists")

        # Validate parent exists
        if parent_id:
            parent = await self.repo.get_by_id(parent_id)
            if not parent:
                raise ValueError(f"Parent organization {parent_id} not found")

        return await self.repo.create(
            name=name,
            code=code,
            parent_id=parent_id,
            description=description,
            created_by=created_by,
            metadata=metadata,
        )

    async def get_organization(self, org_id: uuid.UUID) -> dict[str, Any] | None:
        """Get organization by ID."""
        return await self.repo.get_by_id(org_id)

    async def get_organization_by_code(self, code: str) -> dict[str, Any] | None:
        """Get organization by unique code."""
        return await self.repo.get_by_code(code)

    async def update_organization(self, org_id: uuid.UUID, **updates: Any) -> dict[str, Any] | None:
        """Update organization fields."""
        org = await self.repo.get_by_id(org_id)
        if not org:
            raise ValueError(f"Organization {org_id} not found")

        # If updating code, check for conflicts
        if "code" in updates and updates["code"] != org["code"]:
            existing = await self.repo.get_by_code(updates["code"])
            if existing and existing["id"] != org_id:
                raise ValueError(f"Organization with code '{updates['code']}' already exists")

        return await self.repo.update(org_id, **updates)

    async def delete_organization(self, org_id: uuid.UUID, cascade: bool = False) -> bool:
        """
        Delete organization.

        If cascade=False and org has children, raises ValueError.
        If cascade=True, deletes org and all descendants.
        """
        org = await self.repo.get_by_id(org_id)
        if not org:
            raise ValueError(f"Organization {org_id} not found")

        # Check for children
        children = await self.repo.get_children(org_id, direct_only=True)
        if children and not cascade:
            raise ValueError(
                f"Cannot delete organization with {len(children)} children. "
                "Use cascade=True to delete all descendants."
            )

        return await self.repo.delete(org_id)

    async def move_organization(
        self, org_id: uuid.UUID, new_parent_id: uuid.UUID | None
    ) -> dict[str, Any]:
        """
        Move organization to new parent.

        Validates:
        - Organization exists
        - New parent exists (if provided)
        - No circular references
        """
        org = await self.repo.get_by_id(org_id)
        if not org:
            raise ValueError(f"Organization {org_id} not found")

        if new_parent_id:
            parent = await self.repo.get_by_id(new_parent_id)
            if not parent:
                raise ValueError(f"Parent organization {new_parent_id} not found")

            # Check for circular reference
            if str(org_id) in parent["path"]:
                raise ValueError("Cannot move organization to its own descendant")
        elif org["parent_id"] is not None:
            raise ConflictError("A root organization already exists")

        result = await self.repo.move_organization(org_id, new_parent_id)
        if not result:
            raise ValueError("Failed to move organization")

        return result

    async def list_organizations(
        self,
        skip: int = 0,
        limit: int = 100,
        is_active: bool | None = None,
        parent_id: uuid.UUID | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """List organizations with pagination and filtering."""
        return await self.repo.list_all(
            skip=skip, limit=limit, is_active=is_active, parent_id=parent_id
        )

    async def search_organizations(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        """Search organizations by name, code, or description."""
        if not query or len(query) < 2:
            raise ValueError("Search query must be at least 2 characters")

        return await self.repo.search(query, max_results)

    async def get_organization_tree(
        self, root_id: uuid.UUID | None = None, max_depth: int | None = None
    ) -> dict[str, Any]:
        """
        Get hierarchical tree structure.

        Args:
            root_id: Start from this org (None = all roots)
            max_depth: Maximum depth to traverse (None = unlimited)

        Returns:
            Nested dict with 'children' arrays
        """
        return await self.repo.get_tree(root_id=root_id, max_depth=max_depth)

    async def get_organization_children(
        self, parent_id: uuid.UUID, direct_only: bool = True
    ) -> list[dict[str, Any]]:
        """
        Get child organizations.

        Args:
            parent_id: Parent organization ID
            direct_only: If True, only direct children. If False, all descendants.
        """
        return await self.repo.get_children(parent_id, direct_only=direct_only)

    async def get_organization_ancestors(self, org_id: uuid.UUID) -> list[dict[str, Any]]:
        """Get all ancestor organizations up to root."""
        return await self.repo.get_ancestors(org_id)

    async def get_children_count(self, org_id: uuid.UUID) -> int:
        """Count direct children of organization."""
        children = await self.repo.get_children(org_id, direct_only=True)
        return len(children)

    async def get_descendants_count(self, org_id: uuid.UUID) -> int:
        """Count all descendants of organization."""
        descendants = await self.repo.get_children(org_id, direct_only=False)
        return len(descendants)

    async def get_organization_stats(self) -> dict[str, Any]:
        """
        Get organization statistics.

        Returns statistics like total organizations, total users,
        permissions, and organizations by depth level.
        """
        return await self.repo.get_stats()


# Singleton instance
_organization_service_instance: OrganizationService | None = None


def get_organization_service() -> OrganizationService:
    """Get singleton organization service instance."""
    global _organization_service_instance
    if _organization_service_instance is None:
        _organization_service_instance = OrganizationService()
    return _organization_service_instance
