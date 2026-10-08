"""Draft read/write, version history, and publish endpoints (P3 Tasks 15-16).

Endpoints:
  GET  /agent-definitions/{id}/flow/draft     - the current mutable draft
  GET  /agent-definitions/{id}/flow/published - the currently published flow
  PUT  /agent-definitions/{id}/flow/draft     - save (upsert) the draft
  DELETE /agent-definitions/{id}/flow/draft   - discard the working draft
  GET  /agent-definitions/{id}/flow/versions  - version history, newest first
  GET  /agent-definitions/{id}/flow/versions/{version_no} - one version + spec
  POST /agent-definitions/{id}/flow/publish   - promote the draft to published

Mounted as a separate router from agent_definitions_route (design mirrors P1
Task 6's flow_components_route) because these paths carry their own permission
set (flow:*, P3 Task 18) distinct from agent:*. No path-shadowing risk with
agent_definitions_route's generic GET /{definition_id}: FastAPI's plain
{definition_id} converter matches exactly one path segment, and every route
here is three segments past the shared /agent-definitions prefix.

Auth uses flow:read / flow:update / flow:publish (P3 Task 18's catalog,
user-service migration 0018). Tasks 16/17 used interim agent:read/agent:update
guards before the catalog existed; re-pointed here.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Request, Response

from api.dependencies import AuthenticatedUser, require_permission
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from schemas.flow_version_requests import PublishFlowBody, RollbackFlowBody, SaveDraftBody
from schemas.flows import FlowSpec, FlowVersionDetailResponse, FlowVersionResponse
from service.flows.flow_versions_application_service import FlowVersionsApplicationService

router = APIRouter(prefix="/agent-definitions", tags=["flow-versions"])
_require_read = require_permission("flow:read")
_require_update = require_permission("flow:update")
_require_publish = require_permission("flow:publish")


@router.get("/{definition_id}/flow/draft", response_model=ResponseModel[FlowSpec])
async def get_draft(
    request: Request,
    response: Response,
    definition_id: UUID,
    _user: Annotated[AuthenticatedUser, Depends(_require_read)],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await FlowVersionsApplicationService().get_draft(definition_id=definition_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/{definition_id}/flow/published", response_model=ResponseModel[FlowSpec])
async def get_published(
    request: Request,
    response: Response,
    definition_id: UUID,
    _user: Annotated[AuthenticatedUser, Depends(_require_read)],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await FlowVersionsApplicationService().get_published(definition_id=definition_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.put("/{definition_id}/flow/draft", response_model=ResponseModel[FlowVersionResponse])
async def save_draft(
    request: Request,
    response: Response,
    definition_id: UUID,
    body: SaveDraftBody,
    user: Annotated[AuthenticatedUser, Depends(_require_update)],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await FlowVersionsApplicationService().save_draft(definition_id=definition_id, body=body, user=user),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/{definition_id}/flow/draft", status_code=200, response_model=ResponseModel[None])
async def discard_draft(
    request: Request,
    response: Response,
    definition_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(_require_update)],
) -> ResponseModel[Any]:
    try:
        await FlowVersionsApplicationService().discard_draft(definition_id=definition_id, user=user)
        return ResponseModel(statusCode=200, data=None)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/{definition_id}/flow/versions", response_model=ResponseModel[list[FlowVersionResponse]])
async def list_versions(
    request: Request,
    response: Response,
    definition_id: UUID,
    _user: Annotated[AuthenticatedUser, Depends(_require_read)],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await FlowVersionsApplicationService().list_versions(definition_id=definition_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/{definition_id}/flow/versions/{version_no}", response_model=ResponseModel[FlowVersionDetailResponse])
async def get_version_detail(
    request: Request,
    response: Response,
    definition_id: UUID,
    version_no: int,
    _user: Annotated[AuthenticatedUser, Depends(_require_read)],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await FlowVersionsApplicationService().get_version_detail(
                definition_id=definition_id, version_no=version_no
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/{definition_id}/flow/publish", response_model=ResponseModel[FlowVersionResponse])
async def publish_flow(
    request: Request,
    response: Response,
    definition_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(_require_publish)],
    body: PublishFlowBody | None = None,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await FlowVersionsApplicationService().publish_flow(definition_id=definition_id, user=user, body=body),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/{definition_id}/flow/rollback", response_model=ResponseModel[FlowVersionResponse])
async def rollback_flow(
    request: Request,
    response: Response,
    definition_id: UUID,
    body: RollbackFlowBody,
    user: Annotated[AuthenticatedUser, Depends(_require_publish)],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await FlowVersionsApplicationService().rollback_flow(
                definition_id=definition_id, body=body, user=user
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
