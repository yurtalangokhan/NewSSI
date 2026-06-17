"""
Assistant schema / config endpoint.

GET /assistants/{id}/schemas — returns the graph-specific config
schemas with ``x_oap_ui_config`` metadata consumed by
Open Agent Platform.
"""

import logging

from fastapi import APIRouter, Depends

from controller import AssistantSchemasController, get_assistant_schemas_controller
from api.dependencies import require_user

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_user)])


def _get_controller() -> AssistantSchemasController:
    """Get the singleton AssistantSchemasController instance."""
    return get_assistant_schemas_controller()


@router.get("/assistants/{assistant_id}/schemas")
async def get_assistant_schemas(assistant_id: str) -> dict:
    """
    Get schemas for an assistant's configuration.
    Returns graph-specific config schemas with x_oap_ui_config metadata
    for Open Agent Platform.
    """
    ctrl = _get_controller()
    return await ctrl.get_assistant_schemas(assistant_id)
