"""
Assistant schema / config endpoint.

GET /assistants/{id}/schemas — returns the graph-specific config
schemas with ``x_oap_ui_config`` metadata consumed by
Open Agent Platform.
"""

from typing import Annotated, Any

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Request, Response

from api.dependencies import AuthenticatedUser, require_permission, require_user
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from core.observability.logger import get_logger
from schemas.assistants import AssistantSchemaResponse
from service.orchestration.assistant_schemas_application_service import AssistantSchemasApplicationService
from service.orchestration.assistant_schemas_service import AssistantSchemasService, get_assistant_schemas_service

logger = get_logger(__name__)
router = APIRouter(dependencies=[Depends(require_user)])


def _get_service() -> AssistantSchemasService:
    """Get the singleton AssistantSchemasService instance."""
    return get_assistant_schemas_service()


@router.get("/assistants/{assistant_id}/schemas", response_model=ResponseModel[AssistantSchemaResponse])
async def get_assistant_schemas(
    request: Request,
    response: Response,
    assistant_id: str,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("assistant:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await AssistantSchemasApplicationService(schemas_service=_get_service()).get_assistant_schemas(
                assistant_id=assistant_id
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
