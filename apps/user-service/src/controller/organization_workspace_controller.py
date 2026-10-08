"""HTTP boundary for organization resource workspace requests."""

from typing import Any
import uuid

from config_manager import env

from src.core.exceptions import UnauthorizedError
from src.repository.resource_catalog_client import ResourceCatalogClient
from src.service.organization_workspace_service import OrganizationWorkspaceService
from src.service.resource_permission_service import get_resource_permission_service

from .base import BaseController, translate_domain_errors


class OrganizationWorkspaceController(BaseController):
    def __init__(self, service: OrganizationWorkspaceService):
        self.service = service

    @translate_domain_errors
    async def get_workspace(
        self,
        actor_id: uuid.UUID,
        organization_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
        resource_type: str,
        access_token: str,
    ) -> dict[str, Any]:
        try:
            return await self.service.get_workspace(
                actor_id, organization_id, target_type, target_id, resource_type, access_token
            )
        except UnauthorizedError:
            raise


def get_organization_workspace_controller() -> OrganizationWorkspaceController:
    service = OrganizationWorkspaceService(get_resource_permission_service(), ResourceCatalogClient(env.GATEWAY_URL))
    return OrganizationWorkspaceController(service)
