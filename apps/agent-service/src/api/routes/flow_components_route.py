"""Flow component template, options, and validation endpoints.

Endpoints:
  GET  /flow-components                 - list all templates, grouped by category
  GET  /flow-components/options/{source} - resolve a dynamic options_source
  GET  /flow-components/{type}          - get one template

Auth uses `flow:read` (P3 Task 18's catalog, user-service migration 0018).
P1 Task 6 used interim `agent:list`/`agent:read` guards before the catalog
existed; re-pointed here. The dependency closures are module-level names so
tests can target them directly with `app.dependency_overrides`.
"""

from __future__ import annotations

from typing import Annotated, Any

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Query, Request, Response

from api.dependencies import AuthenticatedUser, require_permission
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from schemas.flows import ComponentTemplate, FlowComponentCatalogResponse, ResolvedOptionsResponse
from service.flows.flow_components_application_service import FlowComponentsApplicationService

router = APIRouter(prefix="/flow-components", tags=["flow-components"])
_require_list = require_permission("flow:read")
_require_read = require_permission("flow:read")


@router.get("", response_model=ResponseModel[FlowComponentCatalogResponse])
async def list_components(
    request: Request, response: Response, _user: Annotated[AuthenticatedUser, Depends(_require_list)]
) -> ResponseModel[Any]:
    try:
        return ResponseModel(statusCode=200, data=await FlowComponentsApplicationService().list_components())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/options/{source}", response_model=ResponseModel[ResolvedOptionsResponse])
async def resolve_component_options(
    request: Request,
    response: Response,
    source: str,
    user: Annotated[AuthenticatedUser, Depends(_require_read)],
    dep: Annotated[list[str] | None, Query()] = None,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await FlowComponentsApplicationService().resolve_component_options(source=source, user=user, dep=dep),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/{component_type}", response_model=ResponseModel[ComponentTemplate])
async def get_component(
    request: Request,
    response: Response,
    component_type: str,
    _user: Annotated[AuthenticatedUser, Depends(_require_read)],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await FlowComponentsApplicationService().get_component(component_type=component_type),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
