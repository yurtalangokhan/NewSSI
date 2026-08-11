"""Business rules for the shared organization canvas layout."""

import uuid
from typing import Any

from src.core.exceptions import ForbiddenError, NotFoundError
from src.repository import OrganizationLayoutRepository


class OrganizationLayoutService:
    """Read and save one shared visual layout for the organization tree."""

    def __init__(self) -> None:
        self.repo = OrganizationLayoutRepository()

    async def get_layout(self, actor_id: uuid.UUID) -> dict[str, Any]:
        """Return all saved positions and the actor's writable organization IDs."""
        positions, writable_ids = await self._get_positions_and_writable_ids(actor_id)
        return {
            "positions": positions,
            "writable_organization_ids": writable_ids,
        }

    async def save_layout(
        self, actor_id: uuid.UUID, positions: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Validate scope for the whole batch, then persist it atomically."""
        if not positions:
            return {"positions": [], "count": 0}

        organization_ids = [position["organization_id"] for position in positions]
        if len(organization_ids) != len(set(organization_ids)):
            raise ValueError("Each organization_id may appear only once")

        requested_ids = set(organization_ids)
        existing_ids = await self.repo.get_existing_organization_ids(requested_ids)
        missing_ids = requested_ids - existing_ids
        if missing_ids:
            missing_id = min(missing_ids, key=str)
            raise NotFoundError(f"Organization {missing_id} not found")

        writable_ids = set(await self.repo.get_writable_organization_ids(actor_id))
        if requested_ids - writable_ids:
            raise ForbiddenError("Actor cannot manage every selected organization")

        saved_positions = await self.repo.bulk_upsert_positions(positions)
        return {"positions": saved_positions, "count": len(saved_positions)}

    async def _get_positions_and_writable_ids(
        self, actor_id: uuid.UUID
    ) -> tuple[list[dict[str, Any]], list[uuid.UUID]]:
        """Fetch independent read datasets while preserving their stable ordering."""
        positions = await self.repo.get_all_positions()
        writable_ids = await self.repo.get_writable_organization_ids(actor_id)
        return positions, writable_ids


_organization_layout_service_instance: OrganizationLayoutService | None = None


def get_organization_layout_service() -> OrganizationLayoutService:
    """Get the shared organization-layout service singleton."""
    global _organization_layout_service_instance
    if _organization_layout_service_instance is None:
        _organization_layout_service_instance = OrganizationLayoutService()
    return _organization_layout_service_instance
