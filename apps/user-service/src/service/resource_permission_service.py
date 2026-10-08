"""Resource permission management service with caching."""

from typing import Any
import uuid

from error_contract import (
    BadRequestError,
    ConflictError,
    DatabaseOperationError,
    render_error_message,
)
from error_contract.identity import ForbiddenError, NotFoundError

from src.repository import (
    OrganizationRepository,
    PermissionAuditRepository,
    ResourcePermissionRepository,
    UserOrganizationRepository,
)
from src.repository.keycloak_resource_authorization import (
    ResourceAuthorizationProjectionRepository,
)
from src.service.organization_scope_service import OrganizationScopeService
from src.service.permission_resolver_service import get_permission_resolver_service
from src.service.user_organization_service import get_user_organization_service

# Permission level hierarchy
PERMISSION_LEVELS = {
    "owner": 100,
    "admin": 80,
    "write": 60,
    "read": 40,
    "execute": 20,
}


class ResourcePermissionService:
    """Business logic for resource permission management."""

    def __init__(
        self,
        permission_repo: ResourcePermissionRepository | None = None,
        organization_repo: OrganizationRepository | None = None,
        user_org_repo: UserOrganizationRepository | None = None,
        audit_repo: PermissionAuditRepository | None = None,
        user_organization_service: Any | None = None,
        authorization_projection: ResourceAuthorizationProjectionRepository | None = None,
    ):
        self.perm_repo = permission_repo or ResourcePermissionRepository()
        self.audit_repo = audit_repo or PermissionAuditRepository()
        self.org_repo = organization_repo or OrganizationRepository()
        self.user_org_repo = user_org_repo or UserOrganizationRepository()
        self.user_organization_service = user_organization_service or get_user_organization_service()
        self.permission_resolver = get_permission_resolver_service()
        self.scope_service = OrganizationScopeService()
        self.authorization_projection = authorization_projection or ResourceAuthorizationProjectionRepository()

    async def check_resource_access(
        self,
        user_id: uuid.UUID,
        resource_type: str,
        resource_id: str,
        required_permission: str = "read",
    ) -> dict[str, Any]:
        """
        Check if user has permission to access resource.

        Priority:
        1. Direct user permission (highest)
        2. Direct permissions on organizations the user belongs to

        Returns:
            {
                "allowed": bool,
                "permission_level": str | None,
                "source": "user" | "organization" | "inherited" | None,
                "organization_id": uuid | None,
                "organization_name": str | None
            }
        """
        candidates = []
        user_perm = await self.perm_repo.get_by_user_resource(user_id, resource_type, resource_id)
        if user_perm:
            candidates.append(
                {
                    "permission_level": user_perm["permission_level"],
                    "source": "user",
                    "organization_id": None,
                    "organization_name": None,
                }
            )
        memberships = await self.user_org_repo.get_user_organizations(user_id, include_inactive=False)
        for membership in memberships:
            org_id = membership["organization_id"]
            permission = await self.perm_repo.get_by_org_resource(org_id, resource_type, resource_id)
            if permission:
                candidates.append(
                    {
                        "permission_level": permission["permission_level"],
                        "source": "organization",
                        "organization_id": org_id,
                        "organization_name": (membership.get("organization") or {}).get("name"),
                    }
                )
        if not candidates:
            return {
                "allowed": False,
                "permission_level": None,
                "source": None,
                "organization_id": None,
                "organization_name": None,
            }
        best = max(
            candidates,
            key=lambda candidate: (
                PERMISSION_LEVELS.get(candidate["permission_level"], 0),
                candidate["source"] == "user",
                str(candidate["organization_id"] or ""),
            ),
        )
        return {"allowed": self._check_level(best["permission_level"], required_permission), **best}

    async def grant_permission(
        self,
        resource_type: str,
        resource_id: str,
        resource_name: str | None = None,
        organization_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        permission_level: str = "read",
        is_inherited: bool = False,
        granted_by: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Grant permission to organization or user."""
        resource_name = resource_name or resource_id
        if not organization_id and not user_id:
            raise BadRequestError(
                message_key="errors.user_service.resource_permission.either_organization_id_or_user_id_must_be_provided"
            )
        if organization_id and user_id:
            raise BadRequestError(
                message_key="errors.user_service.resource_permission.only_one_of_organization_id_or_user_id_can"
            )

        if granted_by is not None:
            await self._authorize_mutation(granted_by, organization_id)
            await self._require_delegable(granted_by, resource_type, resource_id, permission_level)

        # Validate permission level
        if permission_level not in PERMISSION_LEVELS:
            raise BadRequestError(
                message_key="errors.user_service.resource_permission.invalid_permission_level_must_be_one_of",
                message_params={
                    "permission_level": permission_level,
                    "param2": list(PERMISSION_LEVELS.keys()),
                },
            )

        # Check if permission already exists
        if organization_id:
            existing = await self.perm_repo.get_by_org_resource(organization_id, resource_type, resource_id)
        else:
            existing = await self.perm_repo.get_by_user_resource(
                user_id,
                resource_type,
                resource_id,  # type: ignore
            )

        if existing:
            raise ConflictError(
                message_key="errors.user_service.resource_permission.permission_already_exists_for_this_resource_use_update_permission"
            )

        # Create permission
        perm = await self.authorization_projection.project_mutation(
            lambda: self.perm_repo.create(
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=resource_name,
                organization_id=organization_id,
                user_id=user_id,
                permission_level=permission_level,
                is_inherited=is_inherited,
                granted_by=granted_by,
            )
        )

        # Audit log
        await self._log_permission_change(
            action="grant",
            permission=perm,
            performed_by=granted_by,
        )

        return perm

    async def revoke_permission(self, permission_id: uuid.UUID, revoked_by: uuid.UUID | None = None) -> bool:
        """Revoke permission."""
        # Get permission before deleting (for audit)
        perm = await self.perm_repo.get_by_id(permission_id)
        if not perm:
            raise NotFoundError(
                message_key="errors.user_service.resource_permission.permission_not_found",
                message_params={"permission_id": permission_id},
            )

        if revoked_by is not None:
            await self._authorize_mutation(revoked_by, perm.get("organization_id"))
            await self._require_delegable(
                revoked_by, perm["resource_type"], perm["resource_id"], perm["permission_level"]
            )

        # Delete permission
        deleted = await self.authorization_projection.project_mutation(lambda: self.perm_repo.delete(permission_id))

        if deleted:
            # Audit log
            await self._log_permission_change(
                action="revoke",
                permission=perm,
                performed_by=revoked_by,
            )

        return deleted

    async def update_permission(
        self,
        permission_id: uuid.UUID,
        permission_level: str,
        updated_by: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Update permission level."""
        # Get existing permission
        perm = await self.perm_repo.get_by_id(permission_id)
        if not perm:
            raise NotFoundError(
                message_key="errors.user_service.resource_permission.permission_not_found",
                message_params={"permission_id": permission_id},
            )

        if updated_by is not None:
            await self._authorize_mutation(updated_by, perm.get("organization_id"))
            await self._require_delegable(
                updated_by, perm["resource_type"], perm["resource_id"], perm["permission_level"]
            )
            await self._require_delegable(updated_by, perm["resource_type"], perm["resource_id"], permission_level)

        # Validate new level
        if permission_level not in PERMISSION_LEVELS:
            raise BadRequestError(
                message_key="errors.user_service.resource_permission.invalid_permission_level_must_be_one_of",
                message_params={
                    "permission_level": permission_level,
                    "param2": list(PERMISSION_LEVELS.keys()),
                },
            )

        old_level = perm["permission_level"]

        # Update
        updated = await self.authorization_projection.project_mutation(
            lambda: self.perm_repo.update(permission_id, permission_level=permission_level)
        )
        if not updated:
            raise DatabaseOperationError(
                message_key="errors.user_service.resource_permission.failed_to_update_permission"
            )

        # Audit log
        await self._log_permission_change(
            action="update",
            permission=updated,
            performed_by=updated_by,
            old_permission_level=old_level,
        )

        return updated

    async def get_resource_permissions(self, resource_type: str, resource_id: str) -> list[dict[str, Any]]:
        """Get all permissions for a resource (organizations + users)."""
        return await self.perm_repo.get_resource_permissions(resource_type, resource_id)

    async def _authorize_mutation(self, actor_id: uuid.UUID, organization_id: uuid.UUID | None) -> None:
        effective, is_admin = await self.permission_resolver.resolve_effective_access(actor_id)
        if is_admin or "*" in effective:
            return
        if (
            organization_id is None
            or "org:manage-resources" not in effective
            or not (await self.user_organization_service.can_manage_organization(actor_id, organization_id))
        ):
            raise ForbiddenError(
                message_key="errors.user_service.resource_permission.actor_cannot_change_permissions_outside_their_organization_scope"
            )

    async def _require_delegable(self, actor_id, resource_type, resource_id, permission_level):
        effective, is_admin = await self.permission_resolver.resolve_effective_access(actor_id)
        if is_admin or "*" in effective:
            return
        access = await self.check_resource_access(actor_id, resource_type, resource_id, permission_level)
        if not access["allowed"]:
            raise ForbiddenError(
                message_key="errors.user_service.resource_permission.cannot_delegate_a_resource_permission_the_actor_does_not"
            )

    async def check_permission(
        self,
        user_id: uuid.UUID,
        resource_type: str,
        resource_id: str,
        required_permission: str = "read",
    ) -> dict[str, Any]:
        """Backward-compatible alias for resource access checks."""
        return await self.check_resource_access(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            required_permission=required_permission,
        )

    async def get_scoped_direct_permissions(
        self,
        actor_id: uuid.UUID,
        organization_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
        resource_type: str,
    ) -> list[dict[str, Any]]:
        """Return direct permissions for a target that the actor may manage."""
        await self._authorize_scoped_target(
            actor_id,
            organization_id,
            target_type,
            target_id,
            resource_type,
        )
        effective, is_admin = await self.permission_resolver.resolve_effective_access(actor_id)
        if not is_admin and "*" not in effective and "org:read" not in effective:
            raise ForbiddenError(
                message_key="errors.user_service.resource_permission.actor_cannot_read_organization_resources"
            )
        return await self.perm_repo.get_direct_permissions(target_type, target_id, resource_type)

    async def sync_scoped_direct_permissions(
        self,
        actor_id: uuid.UUID,
        organization_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
        resource_type: str,
        desired_permissions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Synchronize direct permissions for one organization-scoped target."""
        await self._authorize_scoped_target(
            actor_id,
            organization_id,
            target_type,
            target_id,
            resource_type,
        )
        desired_by_resource_id = {permission["resource_id"]: permission for permission in desired_permissions}
        if len(desired_by_resource_id) != len(desired_permissions):
            raise BadRequestError(message_key="errors.user_service.resource_permission.resource_ids_must_be_unique")

        effective, is_admin = await self.permission_resolver.resolve_effective_access(actor_id)
        if not is_admin and "*" not in effective:
            if "org:manage-resources" not in effective:
                raise ForbiddenError(
                    message_key="errors.user_service.resource_permission.actor_cannot_manage_organization_resources"
                )
            existing_permissions = await self.perm_repo.get_direct_permissions(target_type, target_id, resource_type)
            changed_existing = [
                permission
                for permission in existing_permissions
                if permission["resource_id"] not in desired_by_resource_id
                or desired_by_resource_id[permission["resource_id"]]["permission_level"]
                != permission["permission_level"]
            ]
            for permission in [*desired_permissions, *changed_existing]:
                access = await self.check_resource_access(
                    actor_id,
                    resource_type,
                    permission["resource_id"],
                    permission["permission_level"],
                )
                if not access["allowed"]:
                    raise ForbiddenError(
                        message_key="errors.user_service.resource_permission.cannot_delegate_a_resource_permission_the_actor_does_not"
                    )

        permissions, changes = await self.authorization_projection.project_scoped_mutation(
            lambda: self.perm_repo.sync_direct_permissions(
                target_type=target_type,
                target_id=target_id,
                resource_type=resource_type,
                desired_permissions=desired_permissions,
                granted_by=actor_id,
            ),
            target_type=target_type,
            target_id=target_id,
            resource_type=resource_type,
            desired_resource_ids=set(desired_by_resource_id),
        )
        for change in changes:
            await self._log_permission_change(
                action=change["action"],
                permission=change["permission"],
                performed_by=actor_id,
                old_permission_level=change.get("old_permission_level"),
            )
        return permissions

    async def _authorize_scoped_target(
        self,
        actor_id: uuid.UUID,
        organization_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
        resource_type: str,
    ) -> None:
        """Validate actor scope and target membership for a scoped permission operation."""
        if target_type not in {"organization", "user"}:
            raise BadRequestError(
                message_key="errors.user_service.resource_permission.target_type_must_be_organization_or_user"
            )
        if resource_type not in {"agent", "rag_collection"}:
            raise BadRequestError(
                message_key="errors.user_service.resource_permission.resource_type_must_be_agent_or_rag_collection"
            )
        if not await self.org_repo.get_by_id(organization_id):
            raise NotFoundError(message_key="errors.user_service.resource_permission.organization_not_found")
        if target_type == "organization" and target_id != organization_id:
            raise BadRequestError(
                message_key="errors.user_service.resource_permission.organization_target_must_match_the_organization_scope"
            )
        if not await self.user_organization_service.can_manage_organization(
            actor_id,
            organization_id,
        ):
            raise ForbiddenError(
                message_key="errors.user_service.resource_permission.actor_cannot_manage_the_selected_organization"
            )
        if target_type == "user" and not await self.user_organization_service.check_user_organization_permission(
            target_id,
            organization_id,
        ):
            raise BadRequestError(
                message_key="errors.user_service.resource_permission.user_target_must_be_an_active_member_of_the"
            )

    async def get_organization_permissions(
        self,
        organization_id: uuid.UUID,
        resource_type: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Get all permissions for an organization, optionally filtered by resource type."""
        if actor_id is not None:
            await self.require_organization_access(actor_id, organization_id)
        return await self.perm_repo.get_organization_permissions(organization_id, resource_type)

    async def require_global_read(self, actor_id: uuid.UUID) -> None:
        effective, is_admin = await self.permission_resolver.resolve_effective_access(actor_id)
        if not is_admin and "*" not in effective:
            raise ForbiddenError(
                message_key="errors.user_service.resource_permission.global_permission_listings_require_a_global_administrator"
            )

    async def require_organization_access(self, actor_id: uuid.UUID, organization_id: uuid.UUID) -> None:
        scope = await self.scope_service.resolve(actor_id)
        scope.require(await self.org_repo.get_by_id(organization_id))

    async def get_user_permissions_listing(
        self, user_id: uuid.UUID, resource_type: str | None = None
    ) -> list[dict[str, Any]]:
        """Get direct permissions for a user, optionally filtered by resource type."""
        return await self.perm_repo.get_user_permissions(user_id, resource_type)

    async def get_user_accessible_resources(
        self, user_id: uuid.UUID, resource_type: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Get all resources user can access.

        Combines direct user permissions and direct permissions on the user's organizations.
        """
        accessible_resources = {}

        # 1. Direct user permissions
        user_perms = await self.perm_repo.get_user_permissions(user_id, resource_type)
        for perm in user_perms:
            key = (perm["resource_type"], perm["resource_id"])
            accessible_resources[key] = {
                **perm,
                "access_via": "direct",
            }

        # 2. Organization permissions
        user_orgs = await self.user_org_repo.get_user_organizations(user_id, include_inactive=False)

        for user_org in user_orgs:
            org_id = user_org["organization_id"]

            # Direct org permissions
            org_perms = await self.perm_repo.get_organization_permissions(org_id, resource_type)
            for perm in org_perms:
                key = (perm["resource_type"], perm["resource_id"])
                existing = accessible_resources.get(key)
                if existing is None or PERMISSION_LEVELS.get(perm["permission_level"], 0) > (
                    PERMISSION_LEVELS.get(existing["permission_level"], 0)
                ):
                    accessible_resources[key] = {
                        **perm,
                        "access_via": "organization",
                    }

        return list(accessible_resources.values())

    async def bulk_grant_permissions(
        self,
        resource_type: str,
        resource_id: str,
        resource_name: str,
        grants: list[dict[str, Any]],
        granted_by: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """
        Bulk grant permissions.

        Args:
            grants: List of dicts with keys:
                - organization_id or user_id
                - permission_level
        """
        results = []
        errors = []

        for grant in grants:
            try:
                perm = await self.grant_permission(
                    resource_type=resource_type,
                    resource_id=resource_id,
                    resource_name=resource_name,
                    organization_id=grant.get("organization_id"),
                    user_id=grant.get("user_id"),
                    permission_level=grant.get("permission_level", "read"),
                    granted_by=granted_by,
                )
                results.append(perm)
            except (BadRequestError, ConflictError, NotFoundError) as e:
                errors.append(
                    {
                        "target": grant.get("organization_id") or grant.get("user_id"),
                        "error": render_error_message(e),
                    }
                )

        return {"successes": results, "errors": errors}

    def _check_level(self, user_level: str, required_level: str) -> bool:
        """Check if user permission level meets requirement."""
        if user_level not in PERMISSION_LEVELS or required_level not in PERMISSION_LEVELS:
            return False
        user_score = PERMISSION_LEVELS.get(user_level, 0)
        required_score = PERMISSION_LEVELS.get(required_level, 0)
        return user_score >= required_score

    async def _log_permission_change(
        self,
        action: str,
        permission: dict[str, Any],
        performed_by: uuid.UUID | None,
        old_permission_level: str | None = None,
    ):
        """Log permission change to audit table."""
        target_type = "organization" if permission["organization_id"] else "user"
        target_id = permission["organization_id"] or permission["user_id"]

        # Get target name
        if target_type == "organization":
            org = await self.org_repo.get_by_id(target_id)
            target_name = org.get("name", "Unknown") if org else "Unknown"
        else:
            # Would need user repo to get name
            target_name = str(target_id)

        await self.audit_repo.create(
            action=action,
            permission_id=permission["id"],
            resource_type=permission["resource_type"],
            resource_id=permission["resource_id"],
            resource_name=permission["resource_name"],
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            permission_level=permission.get("permission_level"),
            old_permission_level=old_permission_level,
            performed_by=performed_by,
            details={
                "is_inherited": permission.get("is_inherited", False),
                "granted_by": str(permission.get("granted_by")) if permission.get("granted_by") else None,
            },
        )


# Singleton instance
_resource_permission_service_instance: ResourcePermissionService | None = None


def get_resource_permission_service() -> ResourcePermissionService:
    """Get singleton resource permission service instance."""
    global _resource_permission_service_instance
    if _resource_permission_service_instance is None:
        _resource_permission_service_instance = ResourcePermissionService()
    return _resource_permission_service_instance
