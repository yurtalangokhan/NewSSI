"""Compose organization assignments with catalogs owned by other services."""

from typing import Any
import uuid

from src.repository.resource_catalog_client import ResourceCatalogClient
from src.service.resource_permission_service import ResourcePermissionService


class OrganizationWorkspaceService:
    def __init__(
        self,
        permissions: ResourcePermissionService,
        catalog: ResourceCatalogClient,
    ):
        self.permissions = permissions
        self.catalog = catalog

    async def get_workspace(
        self,
        actor_id: uuid.UUID,
        organization_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
        resource_type: str,
        access_token: str,
    ) -> dict[str, Any]:
        permissions = await self.permissions.get_scoped_direct_permissions(
            actor_id=actor_id,
            organization_id=organization_id,
            target_type=target_type,
            target_id=target_id,
            resource_type=resource_type,
        )
        resources = await self.catalog.list_resources(resource_type, access_token)
        return {"resources": resources, "permissions": permissions, "count": len(permissions)}
