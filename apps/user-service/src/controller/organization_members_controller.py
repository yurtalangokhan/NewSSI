"""Controller for bulk organization membership reads."""

from typing import Any
import uuid

from src.service import get_user_organization_service

from .base import translate_domain_errors


class OrganizationMembersController:
    """Coordinate bulk direct-membership reads."""

    def __init__(self) -> None:
        self.service = get_user_organization_service()

    @translate_domain_errors
    async def get_active_members_by_organization(self, actor_id: uuid.UUID | None = None) -> dict[str, Any]:
        """Return active direct memberships grouped by organization ID."""
        grouped = await self.service.get_all_active_organization_users(actor_id=actor_id)
        return {
            "members_by_organization": grouped,
            "count": sum(len(members) for members in grouped.values()),
        }


_organization_members_controller_instance: OrganizationMembersController | None = None


def get_organization_members_controller() -> OrganizationMembersController:
    """Get the organization-members controller singleton."""
    global _organization_members_controller_instance
    if _organization_members_controller_instance is None:
        _organization_members_controller_instance = OrganizationMembersController()
    return _organization_members_controller_instance
