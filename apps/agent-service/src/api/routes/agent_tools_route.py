"""Agent Tools routes - bind tools to assistants."""

from typing import Annotated, Any

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Request, Response

from api.dependencies import AuthenticatedUser, require_permission, require_user
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from schemas.agent_tools import AgentToolResponse
from schemas.common import StatusResponse
from service.orchestration.agent_tools_application_service import AgentToolsApplicationService
from service.orchestration.agent_tools_service import AgentToolsService

router = APIRouter(prefix="/assistants", tags=["agent-tools"], dependencies=[Depends(require_user)])


def _get_service() -> AgentToolsService:
    return AgentToolsService.get_instance()


@router.get("/{agent_id}/tools", response_model=ResponseModel[list[AgentToolResponse]])
async def get_agent_tools(
    request: Request,
    response: Response,
    agent_id: int,
    service: Annotated[AgentToolsService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_tool:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AgentToolsApplicationService().get_agent_tools(agent_id=agent_id, service=service),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/{agent_id}/tools", response_model=ResponseModel[list[AgentToolResponse]])
async def add_tools_to_agent(
    request: Request,
    response: Response,
    agent_id: int,
    body: dict[str, Any],
    service: Annotated[AgentToolsService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("assistant:update"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AgentToolsApplicationService().add_tools_to_agent(
                agent_id=agent_id, request=body, service=service
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/{agent_id}/tools/{tool_id}", response_model=ResponseModel[AgentToolResponse])
async def add_tool_to_agent(
    request: Request,
    response: Response,
    agent_id: int,
    tool_id: str,
    service: Annotated[AgentToolsService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("assistant:update"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AgentToolsApplicationService().add_tool_to_agent(
                agent_id=agent_id, tool_id=tool_id, service=service
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/{agent_id}/tools/{tool_id}", response_model=ResponseModel[StatusResponse])
async def remove_tool_from_agent(
    request: Request,
    response: Response,
    agent_id: int,
    tool_id: str,
    service: Annotated[AgentToolsService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("assistant:update"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AgentToolsApplicationService().remove_tool_from_agent(
                agent_id=agent_id, tool_id=tool_id, service=service
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.put("/{agent_id}/tools/reorder", response_model=ResponseModel[list[AgentToolResponse]])
async def reorder_agent_tools(
    request: Request,
    response: Response,
    agent_id: int,
    body: dict[str, Any],
    service: Annotated[AgentToolsService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("assistant:update"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AgentToolsApplicationService().reorder_agent_tools(
                agent_id=agent_id, request=body, service=service
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
