"""HTTP error translation for shared organization layout operations."""

import uuid
from typing import Any

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.service import get_organization_layout_service

from .base import BaseController


class OrganizationLayoutController(BaseController):
    """Coordinate layout requests and translate domain errors for HTTP."""

    def __init__(self) -> None:
        self.service = get_organization_layout_service()

    async def get_layout(self, actor_id: uuid.UUID) -> dict[str, Any]:
        """Return the shared layout and the actor's write scope."""
        return await self.service.get_layout(actor_id)

    async def save_layout(
        self, actor_id: uuid.UUID, positions: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Save all submitted layout coordinates as one atomic update."""
        try:
            return await self.service.save_layout(actor_id, positions)
        except ValueError as error:
            self._raise_bad_request(str(error))
        except ForbiddenError as error:
            self._raise_forbidden(str(error))
        except NotFoundError as error:
            self._raise_not_found(str(error))
        except ConflictError as error:
            self._raise_conflict(str(error))
        raise AssertionError("Unreachable error translation")


_organization_layout_controller_instance: OrganizationLayoutController | None = None


def get_organization_layout_controller() -> OrganizationLayoutController:
    """Get the shared organization-layout controller singleton."""
    global _organization_layout_controller_instance
    if _organization_layout_controller_instance is None:
        _organization_layout_controller_instance = OrganizationLayoutController()
    return _organization_layout_controller_instance
