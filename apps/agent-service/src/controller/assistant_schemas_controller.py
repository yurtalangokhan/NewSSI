"""Assistant schemas controller - handles assistant configuration schemas."""

from typing import Any

from controller.base import BaseController
from service.AssistantSchemasService import AssistantSchemasService


class AssistantSchemasController(BaseController):
    """Controller for assistant configuration schemas."""

    def __init__(self):
        self._service = AssistantSchemasService()

    async def get_assistant_schemas(self, assistant_id: str) -> dict[str, Any]:
        if not assistant_id:
            self._raise_bad_request("assistant_id is required")
        try:
            return await self._service.get_assistant_schemas(assistant_id)
        except ValueError as exc:
            self._raise_bad_request(str(exc))
        except Exception as exc:
            self._raise_internal_error(str(exc))


# Singleton instance
_assistant_schemas_controller: AssistantSchemasController | None = None


def get_assistant_schemas_controller() -> AssistantSchemasController:
    """Get the singleton AssistantSchemasController instance."""
    global _assistant_schemas_controller
    if _assistant_schemas_controller is None:
        _assistant_schemas_controller = AssistantSchemasController()
    return _assistant_schemas_controller
