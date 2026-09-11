"""User-Organization relationship service."""

import uuid
from typing import Any

from src.core.exceptions import ForbiddenError
from src.core.permissions.admin_roles import is_admin_role_name
from src.repository import (
    CompositeRoleRepository,
    OrganizationRepository,
    UserOrganizationRepository,
    UserRepository,
)


class UserOrganizationService:
    """Business logic for user-organization assignments."""

    def __init__(self):
        self.repo = UserOrganizationRepository()
        self.user_repo = UserRepository()
        self.org_repo = OrganizationRepository()
        self.role_repo = CompositeRoleRepository()

    async def assign_user_to_organization(
        self,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        role_in_org: str = "member",
        is_primary: bool = False,
        assigned_by: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Assign user to organization with validation."""
        await self._require_management_scope(assigned_by, organization_id)

        # Validate user exists
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Validate organization exists
        org = await self.org_repo.get_by_id(organization_id)
        if not org:
            raise ValueError(f"Organization {organization_id} not found")

        # Check if already assigned
        existing = await self.repo.get_by_user_and_org(user_id, organization_id)
        if existing:
            raise ValueError(
                f"User {user_id} is already assigned to organization {organization_id}"
            )

        await self._require_valid_organization_role(role_in_org)

        return await self.repo.create(
            user_id=user_id,
            organization_id=organization_id,
            role_in_org=role_in_org,
            is_primary=is_primary,
            assigned_by=assigned_by,
        )

    async def remove_user_from_organization(
        self,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> bool:
        """Remove user from organization."""
        await self._require_management_scope(actor_id, organization_id)
        existing = await self.repo.get_by_user_and_org(user_id, organization_id)
        if not existing:
            raise ValueError(f"User {user_id} is not assigned to organization {organization_id}")

        deleted, _deleted_permissions = await self.repo.delete_and_cleanup_orphan_permissions(
            user_id, organization_id
        )
        return deleted

    async def update_user_organization_role(
        self,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        new_role: str,
        actor_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Update user's role in organization."""
        await self._require_management_scope(actor_id, organization_id)
        user_org = await self.repo.get_by_user_and_org(user_id, organization_id)
        if not user_org:
            raise ValueError(f"User {user_id} is not assigned to organization {organization_id}")

        await self._require_valid_organization_role(new_role)

        updated = await self.repo.update(user_org["id"], role_in_org=new_role)
        if not updated:
            raise ValueError("Failed to update user organization role")

        return updated

    async def set_primary_organization(
        self, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> dict[str, Any]:
        """Set organization as primary for user."""
        user_org = await self.repo.get_by_user_and_org(user_id, organization_id)
        if not user_org:
            raise ValueError(f"User {user_id} is not assigned to organization {organization_id}")

        result = await self.repo.set_primary(user_id, organization_id)
        if not result:
            raise ValueError("Failed to set primary organization")

        return result

    async def get_user_organizations(
        self, user_id: uuid.UUID, include_inactive: bool = False
    ) -> list[dict[str, Any]]:
        """Get all organizations user belongs to."""
        return await self.repo.get_user_organizations(user_id, include_inactive)

    async def get_user_primary_organization(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        """Get user's primary organization."""
        return await self.repo.get_primary_organization(user_id)

    async def get_organization_users(
        self,
        organization_id: uuid.UUID,
        role_in_org: str | None = None,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        """Get all users in organization, optionally filtered by role."""
        return await self.repo.get_organization_users(
            organization_id, role_in_org, include_inactive
        )

    async def get_all_active_organization_users(self) -> dict[str, list[dict[str, Any]]]:
        """Group every active direct membership by organization ID."""
        memberships = await self.repo.get_all_active_organization_users()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for membership in memberships:
            organization_id = str(membership["organization_id"])
            grouped.setdefault(organization_id, []).append(membership)
        return grouped

    async def get_user_managed_organizations(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        """Get organizations where user is unit_manager."""
        all_orgs = await self.repo.get_user_organizations(user_id, include_inactive=False)
        return [org for org in all_orgs if org["role_in_org"] == "unit_manager"]

    async def can_manage_organization(
        self, actor_id: uuid.UUID, organization_id: uuid.UUID
    ) -> bool:
        """Return whether an actor can manage an organization and its subtree."""
        actor = await self.user_repo.get_by_id(actor_id)
        if not actor:
            return False
        role_name = getattr(actor, "role", None)
        if role_name:
            role = await self.role_repo.get_by_name(role_name)
            if role and is_admin_role_name(role.name):
                return True

        # Allow users whose effective permissions include org management.
        from src.service.permission_resolver_service import get_permission_resolver_service

        effective = set(
            await get_permission_resolver_service().resolve_effective_permissions(actor_id)
        )
        if "*" in effective or effective.intersection(
            {"org:update", "org:create", "org:delete", "org:move", "org:manage-users"}
        ):
            return True

        target = await self.org_repo.get_by_id(organization_id)
        if not target:
            return False

        managers = await self.repo.get_active_unit_manager_organizations(actor_id)
        target_path = target.get("path")
        for manager in managers:
            managed_organization_id = manager["organization_id"]
            if managed_organization_id == organization_id:
                return True
            if target_path and f"/{managed_organization_id}/" in target_path:
                return True
        return False

    async def _require_management_scope(
        self, actor_id: uuid.UUID | None, organization_id: uuid.UUID
    ) -> None:
        """Raise when the actor is not authorized to manage the target organization."""
        if actor_id is None or not await self.can_manage_organization(actor_id, organization_id):
            raise ForbiddenError("Actor cannot manage the selected organization")

    async def _require_valid_organization_role(self, role_name: str) -> None:
        """Accept Unit Manager or a role from the authoritative catalog."""
        if role_name == "unit_manager":
            return
        if await self.role_repo.get_by_name(role_name):
            return
        raise ValueError(f"Unknown organization role '{role_name}'")

    async def check_user_organization_permission(
        self,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        required_role: str | None = None,
    ) -> bool:
        """
        Check if user has access to organization.

        Args:
            user_id: User ID
            organization_id: Organization ID
            required_role: If specified, check if user has this role or higher

        Returns:
            True if user has access
        """
        user_org = await self.repo.get_by_user_and_org(user_id, organization_id)
        if not user_org or not user_org["is_active"]:
            return False

        if not required_role:
            return True

        return user_org["role_in_org"] == required_role

    async def is_unit_manager(self, user_id: uuid.UUID, organization_id: uuid.UUID) -> bool:
        """Check if user is unit manager of organization."""
        return await self.check_user_organization_permission(
            user_id, organization_id, required_role="unit_manager"
        )

    async def count_organization_users(self, organization_id: uuid.UUID) -> int:
        """Count active users in organization."""
        return await self.repo.count_organization_users(organization_id)

    async def bulk_assign_users(
        self,
        user_ids: list[uuid.UUID],
        organization_id: uuid.UUID,
        role_in_org: str = "member",
        assigned_by: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Assign multiple users to organization at once."""
        results = []
        errors = []

        for user_id in user_ids:
            try:
                result = await self.assign_user_to_organization(
                    user_id=user_id,
                    organization_id=organization_id,
                    role_in_org=role_in_org,
                    assigned_by=assigned_by,
                )
                results.append(result)
            except ValueError as e:
                errors.append({"user_id": user_id, "error": str(e)})

        return {"successes": results, "errors": errors}


# Singleton instance
_user_organization_service_instance: UserOrganizationService | None = None


def get_user_organization_service() -> UserOrganizationService:
    """Get singleton user organization service instance."""
    global _user_organization_service_instance
    if _user_organization_service_instance is None:
        _user_organization_service_instance = UserOrganizationService()
    return _user_organization_service_instance
