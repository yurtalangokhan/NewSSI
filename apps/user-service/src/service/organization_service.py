"""Organization management service."""

from typing import Any
import uuid

from error_contract import BadRequestError, DatabaseOperationError, NotFoundError
from error_contract.identity import ConflictError

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
            raise ConflictError(
                message_key="errors.user_service.organization.organization_with_code_already_exists",
                message_params={"code": code},
            )

        # The enterprise hierarchy has exactly one root.  Any existing
        # organization implies the root has already been established.
        if parent_id is None:
            _organizations, total = await self.repo.list_all(skip=0, limit=1)
            if total:
                raise ConflictError(message_key="errors.user_service.organization.a_root_organization_already_exists")

        # Validate parent exists
        if parent_id:
            parent = await self.repo.get_by_id(parent_id)
            if not parent:
                raise NotFoundError(
                    message_key="errors.user_service.organization.parent_organization_not_found",
                    message_params={"parent_id": parent_id},
                )

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

    async def update_organization(self, org_id: uuid.UUID, **updates: Any) -> dict[str, Any] | None:
        """Update organization fields."""
        org = await self.repo.get_by_id(org_id)
        if not org:
            raise NotFoundError(
                message_key="errors.user_service.organization.organization_not_found",
                message_params={"org_id": org_id},
            )

        # If updating code, check for conflicts
        if "code" in updates and updates["code"] != org["code"]:
            existing = await self.repo.get_by_code(updates["code"])
            if existing and existing["id"] != org_id:
                raise ConflictError(
                    message_key="errors.user_service.organization.organization_with_code_already_exists",
                    message_params={"param1": updates["code"]},
                )

        return await self.repo.update(org_id, **updates)

    async def delete_organization(self, org_id: uuid.UUID, cascade: bool = False) -> bool:
        """
        Delete organization.

        If cascade=False and org has children, raises ValueError.
        If cascade=True, deletes org and all descendants.
        """
        org = await self.repo.get_by_id(org_id)
        if not org:
            raise NotFoundError(
                message_key="errors.user_service.organization.organization_not_found",
                message_params={"org_id": org_id},
            )

        # Check for children
        children = await self.repo.get_children(org_id, direct_only=True)
        if children and not cascade:
            raise ConflictError(
                message_key="errors.user_service.organization.cannot_delete_organization_with_children_use_cascade_true_to",
                message_params={"param1": len(children)},
            )

        return await self.repo.delete(org_id)

    async def move_organization(self, org_id: uuid.UUID, new_parent_id: uuid.UUID | None) -> dict[str, Any]:
        """
        Move organization to new parent.

        Validates:
        - Organization exists
        - New parent exists (if provided)
        - No circular references
        """
        org = await self.repo.get_by_id(org_id)
        if not org:
            raise NotFoundError(
                message_key="errors.user_service.organization.organization_not_found",
                message_params={"org_id": org_id},
            )

        if new_parent_id:
            parent = await self.repo.get_by_id(new_parent_id)
            if not parent:
                raise NotFoundError(
                    message_key="errors.user_service.organization.parent_organization_not_found",
                    message_params={"new_parent_id": new_parent_id},
                )

            # Check for circular reference
            if str(org_id) in parent["path"]:
                raise BadRequestError(
                    message_key="errors.user_service.organization.cannot_move_organization_to_its_own_descendant"
                )
        elif org["parent_id"] is not None:
            raise ConflictError(message_key="errors.user_service.organization.a_root_organization_already_exists")

        result = await self.repo.move_organization(org_id, new_parent_id)
        if not result:
            raise DatabaseOperationError(message_key="errors.user_service.organization.failed_to_move_organization")

        return result

    async def list_organizations(
        self,
        skip: int = 0,
        limit: int = 100,
        is_active: bool | None = None,
        parent_id: uuid.UUID | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """List organizations with pagination and filtering."""
        return await self.repo.list_all(skip=skip, limit=limit, is_active=is_active, parent_id=parent_id)

    async def search_organizations(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        """Search organizations by name, code, or description."""
        if not query or len(query) < 2:
            raise BadRequestError(
                message_key="errors.user_service.organization.search_query_must_be_at_least_characters"
            )

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

    async def get_organization_children(self, parent_id: uuid.UUID, direct_only: bool = True) -> list[dict[str, Any]]:
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
