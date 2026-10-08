"""User-Organization relationship service."""

from typing import Any
import uuid

from error_contract import (
    BadRequestError,
    ConflictError,
    DatabaseOperationError,
    NotFoundError,
    render_error_message,
)
from error_contract.identity import ForbiddenError

from src.repository import (
    CompositeRoleRepository,
    OrganizationRepository,
    UserOrganizationRepository,
    UserRepository,
    UserRoleRepository,
)
from src.service.organization_scope_service import OrganizationScopeService
from src.service.permission_resolver_service import get_permission_resolver_service
from src.service.user_service import get_user_service


class UserOrganizationService:
    """Business logic for user-organization assignments."""

    def __init__(self):
        self.repo = UserOrganizationRepository()
        self.user_repo = UserRepository()
        self.user_role_repo = UserRoleRepository()
        self.user_service = get_user_service()
        self.org_repo = OrganizationRepository()
        self.role_repo = CompositeRoleRepository()
        self.permission_resolver = get_permission_resolver_service()
        self.scope_service = OrganizationScopeService()

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
            raise NotFoundError(
                message_key="errors.user_service.user_organization.user_not_found",
                message_params={"user_id": user_id},
            )

        # Validate organization exists
        org = await self.org_repo.get_by_id(organization_id)
        if not org:
            raise NotFoundError(
                message_key="errors.user_service.user_organization.organization_not_found",
                message_params={"organization_id": organization_id},
            )

        # Check if already assigned
        existing = await self.repo.get_by_user_and_org(user_id, organization_id)
        if existing and existing["is_active"]:
            raise ConflictError(
                message_key="errors.user_service.user_organization.user_is_already_assigned_to_organization",
                message_params={"user_id": user_id, "organization_id": organization_id},
            )

        role_in_org = await self._require_valid_organization_role(role_in_org)
        await self._require_delegable_role(assigned_by, user_id, role_in_org)

        effective, is_admin = await self.permission_resolver.resolve_effective_access(assigned_by)
        if not is_admin and "*" not in effective:
            scope = await self.scope_service.resolve(assigned_by)
            candidates, _ = await self.user_repo.list_assignable(
                organization_id, root_ids=scope.root_ids, user_id=user_id, limit=1
            )
            if not candidates:
                raise ForbiddenError(message_key="errors.user_service.common.forbidden")

        if not await self.user_service.set_user_role(user_id, role_in_org):
            raise DatabaseOperationError(message_key="errors.user_service.user_organization.failed_to_update_user_role")
        if existing:
            result = await self.repo.update_by_user_and_org(
                user_id,
                organization_id,
                is_primary=is_primary,
                is_active=True,
                assigned_by=assigned_by,
            )

        else:
            result = await self.repo.create(
                user_id=user_id,
                organization_id=organization_id,
                is_primary=is_primary,
                assigned_by=assigned_by,
            )
        return self._present_role(result, role_in_org)

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
            raise NotFoundError(
                message_key="errors.user_service.user_organization.user_is_not_assigned_to_organization",
                message_params={"user_id": user_id, "organization_id": organization_id},
            )

        deleted, _deleted_permissions = await self.repo.delete_and_cleanup_orphan_permissions(user_id, organization_id)
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
            raise NotFoundError(
                message_key="errors.user_service.user_organization.user_is_not_assigned_to_organization",
                message_params={"user_id": user_id, "organization_id": organization_id},
            )

        new_role = await self._require_valid_organization_role(new_role)
        await self._require_delegable_role(actor_id, user_id, new_role)

        updated = await self.user_service.set_user_role(user_id, new_role)
        if not updated:
            raise DatabaseOperationError(message_key="errors.user_service.user_organization.failed_to_update_user_role")
        return self._present_role(user_org, new_role)

    async def set_primary_organization(self, user_id: uuid.UUID, organization_id: uuid.UUID) -> dict[str, Any]:
        """Set organization as primary for user."""
        user_org = await self.repo.get_by_user_and_org(user_id, organization_id)
        if not user_org:
            raise NotFoundError(
                message_key="errors.user_service.user_organization.user_is_not_assigned_to_organization",
                message_params={"user_id": user_id, "organization_id": organization_id},
            )

        result = await self.repo.set_primary(user_id, organization_id)
        if not result:
            raise DatabaseOperationError(
                message_key="errors.user_service.user_organization.failed_to_set_primary_organization"
            )

        return (await self._with_user_roles([result]))[0]

    async def get_user_organizations(self, user_id: uuid.UUID, include_inactive: bool = False) -> list[dict[str, Any]]:
        """Get all organizations user belongs to."""
        return await self._with_user_roles(await self.repo.get_user_organizations(user_id, include_inactive))

    async def get_user_primary_organization(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        """Get user's primary organization."""
        membership = await self.repo.get_primary_organization(user_id)
        return (await self._with_user_roles([membership]))[0] if membership else None

    async def get_organization_users(
        self,
        organization_id: uuid.UUID,
        role_in_org: str | None = None,
        include_inactive: bool = False,
        actor_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Get all users in organization, optionally filtered by role."""
        if actor_id is not None:
            scope = await self.scope_service.resolve(actor_id)
            scope.require(await self.org_repo.get_by_id(organization_id))
        memberships = await self._with_user_roles(
            await self.repo.get_organization_users(organization_id, include_inactive)
        )
        return [
            item
            for item in memberships
            if not role_in_org or self._normalize_role(item["role_in_org"]) == self._normalize_role(role_in_org)
        ]

    async def get_all_active_organization_users(
        self, actor_id: uuid.UUID | None = None
    ) -> dict[str, list[dict[str, Any]]]:
        """Group every active direct membership by organization ID."""
        memberships = await self.repo.get_all_active_organization_users()
        allowed_ids = None
        if actor_id is not None:
            scope = await self.scope_service.resolve(actor_id)
            if not scope.global_access:
                allowed_ids = {str(org["id"]) for org in await self.org_repo.get_scoped_organizations(scope.root_ids)}
        grouped: dict[str, list[dict[str, Any]]] = {}
        memberships = await self._with_user_roles(
            [item for item in memberships if allowed_ids is None or str(item["organization_id"]) in allowed_ids]
        )
        for membership in memberships:
            organization_id = str(membership["organization_id"])
            if allowed_ids is None or organization_id in allowed_ids:
                grouped.setdefault(organization_id, []).append(membership)
        return grouped

    @staticmethod
    def _present_role(membership, role):
        result = {**membership, "role_in_org": role or ""}
        if membership.get("user"):
            result["user"] = {**membership["user"], "role": role}
        return result

    async def _with_user_roles(self, memberships):
        roles = (
            await self.user_role_repo.get_primary_roles([uuid.UUID(str(item["user_id"])) for item in memberships])
            if memberships
            else {}
        )
        return [self._present_role(item, roles.get(uuid.UUID(str(item["user_id"])))) for item in memberships]

    async def get_user_managed_organizations(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        """Get organizations where user is unit_manager."""
        return await self._with_user_roles(await self.repo.get_active_unit_manager_organizations(user_id))

    async def can_manage_organization(self, actor_id: uuid.UUID, organization_id: uuid.UUID) -> bool:
        """Return whether an actor can manage an organization and its subtree."""
        effective, is_admin = await self.permission_resolver.resolve_effective_access(actor_id)
        if is_admin or "*" in effective:
            return True
        if not set(effective).intersection(
            {
                "org:update",
                "org:create",
                "org:delete",
                "org:move",
                "org:manage-users",
                "org:manage-resources",
            }
        ):
            return False

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

    async def _require_management_scope(self, actor_id: uuid.UUID | None, organization_id: uuid.UUID) -> None:
        """Raise when the actor is not authorized to manage the target organization."""
        if actor_id is None or not await self.can_manage_organization(actor_id, organization_id):
            raise ForbiddenError(
                message_key="errors.user_service.user_organization.actor_cannot_manage_the_selected_organization"
            )
        effective, is_admin = await self.permission_resolver.resolve_effective_access(actor_id)
        if not is_admin and "*" not in effective and "org:manage-users" not in effective:
            raise ForbiddenError(
                message_key="errors.user_service.user_organization.actor_cannot_manage_organization_members"
            )

    async def get_assignable_users(
        self,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
        query: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search eligible identities before applying the result bound."""
        await self._require_management_scope(actor_id, organization_id)
        scope = await self.scope_service.resolve(actor_id)
        scope.require(await self.org_repo.get_by_id(organization_id))
        users, total = await self.user_repo.list_assignable(
            organization_id,
            root_ids=None if scope.global_access else scope.root_ids,
            query=query.strip(),
            limit=max(1, min(limit, 100)),
        )
        return {"users": users, "total": total}

    async def _require_delegable_role(self, actor_id, target_user_id, role_name):
        effective, is_admin = await self.permission_resolver.resolve_effective_access(actor_id)
        if is_admin or "*" in effective:
            return
        assignments = await self.user_role_repo.list_user_roles(target_user_id)
        if (
            actor_id == target_user_id
            or self._normalize_role(role_name) != "enduser"
            or any(self._normalize_role(str(item["name"])) != "enduser" for item in assignments)
        ):
            raise ForbiddenError(message_key="errors.user_service.common.forbidden")

    @staticmethod
    def _normalize_role(role_name: str) -> str:
        return "".join(role_name.lower().replace("_", "").replace("-", "").split())

    async def _require_valid_organization_role(self, role_name: str) -> str:
        """Accept Unit Manager or a role from the authoritative catalog."""
        normalized = self._normalize_role(role_name)
        if normalized in {"systemadmin", "enterpriseadmin"}:
            raise ForbiddenError(message_key="errors.user_service.common.forbidden")
        names = [role_name]
        if normalized == "unitmanager":
            names = ["Unit Manager", "unit-manager", "unit_manager", "unitmanager"]
        if normalized == "enduser":
            names = ["enduser", "end-user", "End User", "end_user"]
        for name in names:
            role = await self.role_repo.get_by_name(name)
            if role:
                return role.name
        raise BadRequestError(
            message_key="errors.user_service.user_organization.unknown_organization_role",
            message_params={"role_name": role_name},
        )

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

        assignments = await self.user_role_repo.list_user_roles(user_id)
        return any(
            self._normalize_role(str(item["name"])) == self._normalize_role(required_role) for item in assignments
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
            except (BadRequestError, ConflictError, NotFoundError, ForbiddenError) as e:
                errors.append({"user_id": user_id, "error": render_error_message(e)})

        return {"successes": results, "errors": errors}


# Singleton instance
_user_organization_service_instance: UserOrganizationService | None = None


def get_user_organization_service() -> UserOrganizationService:
    """Get singleton user organization service instance."""
    global _user_organization_service_instance
    if _user_organization_service_instance is None:
        _user_organization_service_instance = UserOrganizationService()
    return _user_organization_service_instance
