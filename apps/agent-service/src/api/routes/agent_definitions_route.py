"""Agent Definitions CRUD API.

Endpoints:
  POST   /agent-definitions                    - Create a new dynamic agent definition
  GET    /agent-definitions                    - List all agent definitions
  POST   /agent-definitions/validate-composition     - Validate agent composition
  POST   /agent-definitions/available-for-composition - List agents for composition (with schema filter)
  POST   /agent-definitions/validate-flow            - Validate a FlowSpec without persisting
  GET    /agent-definitions/{id}/composition-info    - Get hierarchical composition structure
  PUT    /agent-definitions/{id}/sub-agents          - Update sub-agents with validation
  GET    /agent-definitions/{id}               - Get a single agent definition
  PUT    /agent-definitions/{id}               - Update an agent definition
  DELETE /agent-definitions/{id}               - Delete an agent definition
  GET    /agent-definitions/schemas/list      - Available graph schemas
  GET    /agent-definitions/brains/list       - Available brain types
  GET    /agent-definitions/memory/list       - Available memory types

IMPORTANT: Route order matters! Specific literal routes MUST come before generic {id} routes.
- Metadata routes: schemas/list, brains/list, memory/list
- CRUD routes: POST "", GET ""
- Specific composition routes: validate-composition, available-for-composition
- Flow routes: validate-flow
- Routes with path params but specific: {id}/composition-info, {id}/sub-agents
- Generic routes: {id}, {id}, {id}
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Request, Response, status

from api.dependencies import AuthenticatedUser, require_permission, require_user
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from schemas.agent_definitions import (
    AgentDefinitionResponse,
    AvailableForCompositionItemResponse,
    ComponentTypeItemResponse,
    CompositionInfoResponse,
    CompositionValidationResponse,
    CreateAgentDefinitionRequest,
    FlowExpansionResponse,
    FlowValidationResponse,
    GraphSchemaItemResponse,
    UpdateAgentDefinitionRequest,
)
from schemas.common import StatusResponse
from service.agent_definitions.agent_definitions_application_service import AgentDefinitionsApplicationService

router = APIRouter(prefix="/agent-definitions", tags=["agent-definitions"], dependencies=[Depends(require_user)])


@router.get("/schemas/list", response_model=ResponseModel[list[GraphSchemaItemResponse]])
async def list_schemas(
    request: Request, response: Response, _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:list"))]
) -> ResponseModel[Any]:
    try:
        return ResponseModel(statusCode=200, data=await AgentDefinitionsApplicationService().list_schemas())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/brains/list", response_model=ResponseModel[list[ComponentTypeItemResponse]])
async def list_brain_types(
    request: Request, response: Response, _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:list"))]
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AgentDefinitionsApplicationService().list_brain_types(),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/memory/list", response_model=ResponseModel[list[ComponentTypeItemResponse]])
async def list_memory_types(
    request: Request, response: Response, _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:list"))]
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AgentDefinitionsApplicationService().list_memory_types(),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ResponseModel[AgentDefinitionResponse])
async def create_agent_definition(
    request: Request,
    response: Response,
    body: CreateAgentDefinitionRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("agent:create"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=201,
            data=await AgentDefinitionsApplicationService().create_agent_definition(body=body, user=user),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("", response_model=ResponseModel[list[AgentDefinitionResponse]])
async def list_agent_definitions(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:list"))],
    graph_schema: str | None = None,
    active_only: bool = True,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AgentDefinitionsApplicationService().list_agent_definitions(
                graph_schema=graph_schema, active_only=active_only
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/validate-composition", response_model=ResponseModel[CompositionValidationResponse])
async def validate_composition(
    request: Request,
    response: Response,
    body: dict[str, Any],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AgentDefinitionsApplicationService().validate_composition(body=body),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/available-for-composition", response_model=ResponseModel[list[AvailableForCompositionItemResponse]])
async def get_available_for_composition(
    request: Request,
    response: Response,
    body: dict[str, Any],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AgentDefinitionsApplicationService().get_available_for_composition(body=body),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/validate-flow", response_model=ResponseModel[FlowValidationResponse])
async def validate_flow(
    request: Request,
    response: Response,
    body: dict[str, Any],
    user: Annotated[AuthenticatedUser, Depends(require_permission("flow:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AgentDefinitionsApplicationService().validate_flow(body=body, user=user),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/{definition_id}/composition-info", response_model=ResponseModel[CompositionInfoResponse])
async def get_composition_info(
    request: Request,
    response: Response,
    definition_id: UUID,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AgentDefinitionsApplicationService().get_composition_info(definition_id=definition_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.put("/{definition_id}/sub-agents", response_model=ResponseModel[AgentDefinitionResponse])
async def update_sub_agents(
    request: Request,
    response: Response,
    definition_id: UUID,
    body: dict[str, Any],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:update"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AgentDefinitionsApplicationService().update_sub_agents(definition_id=definition_id, body=body),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/{definition_id}/expand", response_model=ResponseModel[FlowExpansionResponse])
async def expand_agent_definition_route(
    request: Request,
    response: Response,
    definition_id: UUID,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:create"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AgentDefinitionsApplicationService().expand_agent_definition(definition_id=definition_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/{definition_id}", response_model=ResponseModel[AgentDefinitionResponse])
async def get_agent_definition(
    request: Request,
    response: Response,
    definition_id: UUID,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AgentDefinitionsApplicationService().get_agent_definition(definition_id=definition_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.put("/{definition_id}", response_model=ResponseModel[AgentDefinitionResponse])
async def update_agent_definition(
    request: Request,
    response: Response,
    definition_id: UUID,
    body: UpdateAgentDefinitionRequest,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:update"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AgentDefinitionsApplicationService().update_agent_definition(
                definition_id=definition_id, body=body
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/{definition_id}", status_code=status.HTTP_200_OK, response_model=ResponseModel[StatusResponse])
async def delete_agent_definition(
    request: Request,
    response: Response,
    definition_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_permission("agent:delete"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AgentDefinitionsApplicationService().delete_agent_definition(
                definition_id=definition_id, user=user
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
