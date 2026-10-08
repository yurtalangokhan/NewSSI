"""HTTP error translation for user-organization relationship operations."""

from typing import Any
import uuid

from error_contract.identity import ForbiddenError

from src.service import get_user_organization_service

from .base import BaseController, translate_domain_errors


class UserOrganizationController(BaseController):
    """Coordinate user-organization requests and translate domain errors for HTTP."""

    def __init__(self) -> None:
        self.service = get_user_organization_service()

    @translate_domain_errors
    async def get_assignable_users(
        self,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
        query: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        return await self.service.get_assignable_users(organization_id, actor_id, query, limit)

    @translate_domain_errors
    async def get_organization_users(
        self,
        organization_id: uuid.UUID,
        role_in_org: str | None = None,
        include_inactive: bool = False,
        actor_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        users = await self.service.get_organization_users(
            organization_id, role_in_org, include_inactive, actor_id=actor_id
        )
        return {"users": users, "count": len(users)}

    @translate_domain_errors
    async def assign_user_to_organization(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        role_in_org: str,
        is_primary: bool,
        assigned_by: uuid.UUID,
    ) -> dict[str, Any]:
        try:
            return await self.service.assign_user_to_organization(
                user_id=user_id,
                organization_id=organization_id,
                role_in_org=role_in_org,
                is_primary=is_primary,
                assigned_by=assigned_by,
            )
        except ForbiddenError:
            raise

    @translate_domain_errors
    async def bulk_assign_users(
        self,
        organization_id: uuid.UUID,
        user_ids: list[uuid.UUID],
        role_in_org: str,
        assigned_by: uuid.UUID,
    ) -> dict[str, Any]:
        try:
            result = await self.service.bulk_assign_users(
                user_ids=user_ids,
                organization_id=organization_id,
                role_in_org=role_in_org,
                assigned_by=assigned_by,
            )
            return result
        except ForbiddenError:
            raise

    @translate_domain_errors
    async def update_user_organization(
        self,
        organization_id: uuid.UUID,
        target_user_id: uuid.UUID,
        new_role: str | None,
        actor_id: uuid.UUID,
    ) -> dict[str, Any]:
        try:
            if new_role:
                return await self.service.update_user_organization_role(
                    user_id=target_user_id,
                    organization_id=organization_id,
                    new_role=new_role,
                    actor_id=actor_id,
                )
            else:
                self._raise_bad_request("common.bad_request")
        except ForbiddenError:
            raise

    @translate_domain_errors
    async def remove_user_from_organization(
        self,
        organization_id: uuid.UUID,
        target_user_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        try:
            deleted = await self.service.remove_user_from_organization(
                target_user_id, organization_id, actor_id=actor_id
            )
            if not deleted:
                self._raise_not_found("user_organization.not_found")
            return {"success": True}
        except ForbiddenError:
            raise

    @translate_domain_errors
    async def get_user_organizations(self, user_id: uuid.UUID, include_inactive: bool = False) -> dict[str, Any]:
        orgs = await self.service.get_user_organizations(user_id, include_inactive)
        return {"organizations": orgs, "count": len(orgs)}

    @translate_domain_errors
    async def get_my_organizations(self, user_id: uuid.UUID, include_inactive: bool = False) -> dict[str, Any]:
        orgs = await self.service.get_user_organizations(user_id, include_inactive)
        return {"organizations": orgs, "count": len(orgs)}

    @translate_domain_errors
    async def set_primary_organization(self, user_id: uuid.UUID, organization_id: uuid.UUID) -> dict[str, Any]:
        return await self.service.set_primary_organization(user_id, organization_id)

    @translate_domain_errors
    async def get_primary_organization(self, user_id: uuid.UUID) -> dict[str, Any]:
        org = await self.service.get_user_primary_organization(user_id)
        if not org:
            self._raise_not_found("organization.primary_not_found")
        return org

    @translate_domain_errors
    async def get_managed_organizations(self, user_id: uuid.UUID) -> dict[str, Any]:
        orgs = await self.service.get_user_managed_organizations(user_id)
        return {"organizations": orgs, "count": len(orgs)}


_user_organization_controller_instance: UserOrganizationController | None = None


def get_user_organization_controller() -> UserOrganizationController:
    """Get the user-organization controller singleton."""
    global _user_organization_controller_instance
    if _user_organization_controller_instance is None:
        _user_organization_controller_instance = UserOrganizationController()
    return _user_organization_controller_instance
