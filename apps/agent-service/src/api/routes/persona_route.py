"""
Persona/Assistant routes.

Endpoints: /api/persona/* (personas/assistants management)
"""

from typing import Annotated

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Depends, File, Request, Response, UploadFile

from api.dependencies import AuthenticatedUser, extract_auth_token_from_request, require_permission, require_user
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from schemas.common import DeleteResponse
from schemas.personas import (
    PersonaImageUploadResponse,
    PersonaLabelResponse,
    PersonaOptionResponse,
    PersonaResponse,
    PersonaUpsertRequest,
)
from service.personas import PersonaService, get_persona_service

router = APIRouter(tags=["persona"], dependencies=[Depends(require_user)])


def _get_service() -> PersonaService:
    return get_persona_service()


@router.get("/api/persona", response_model=ResponseModel[list[PersonaResponse]])
async def get_personas(
    http_request: Request,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(require_permission("persona:read"))],
):
    try:
        return ResponseModel(data=await _get_service().get_personas(user))
    except ApplicationError as error:
        set_error_response(response, error, http_request)
        message = render_error_message(error, locale=request_locale(http_request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/persona/options", response_model=ResponseModel[list[PersonaOptionResponse]])
async def get_persona_options(
    http_request: Request,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(require_permission("persona:read"))],
):
    try:
        return ResponseModel(data=await _get_service().get_persona_options(user))
    except ApplicationError as error:
        set_error_response(response, error, http_request)
        message = render_error_message(error, locale=request_locale(http_request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/persona/labels", response_model=ResponseModel[list[PersonaLabelResponse]])
async def get_persona_labels(
    http_request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("persona:read"))],
):
    try:
        return ResponseModel(data=await _get_service().get_persona_labels())
    except ApplicationError as error:
        set_error_response(response, error, http_request)
        message = render_error_message(error, locale=request_locale(http_request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/persona", response_model=ResponseModel[PersonaResponse])
async def create_persona(
    http_request: Request,
    response: Response,
    persona_request: PersonaUpsertRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("persona:create"))],
):
    try:
        return ResponseModel(
            data=await _get_service().create_persona(
                persona_request.model_dump(), auth_token=extract_auth_token_from_request(http_request), user=user
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, http_request)
        message = render_error_message(error, locale=request_locale(http_request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/persona/{persona_id}", response_model=ResponseModel[PersonaResponse])
async def get_persona(
    http_request: Request,
    response: Response,
    persona_id: int,
    user: Annotated[AuthenticatedUser, Depends(require_permission("persona:read"))],
):
    try:
        return ResponseModel(data=await _get_service().get_persona(persona_id, user))
    except ApplicationError as error:
        set_error_response(response, error, http_request)
        message = render_error_message(error, locale=request_locale(http_request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.patch("/api/persona/{persona_id}", response_model=ResponseModel[PersonaResponse])
async def update_persona(
    http_request: Request,
    response: Response,
    persona_id: int,
    request: PersonaUpsertRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("persona:update"))],
):
    try:
        payload = request.model_dump()
        if "connector_bindings" not in request.model_fields_set:
            payload.pop("connector_bindings", None)
        return ResponseModel(data=await _get_service().update_persona(persona_id, payload, user_id=user.user_id))
    except ApplicationError as error:
        set_error_response(response, error, http_request)
        message = render_error_message(error, locale=request_locale(http_request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/api/persona/{persona_id}", response_model=ResponseModel[DeleteResponse])
async def delete_persona(
    http_request: Request,
    response: Response,
    persona_id: int,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("persona:delete"))],
):
    try:
        return ResponseModel(data=await _get_service().delete_persona(persona_id))
    except ApplicationError as error:
        set_error_response(response, error, http_request)
        message = render_error_message(error, locale=request_locale(http_request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/admin/persona/upload-image", response_model=ResponseModel[PersonaImageUploadResponse])
async def upload_persona_image(
    http_request: Request,
    response: Response,
    file: Annotated[UploadFile, File()],
    user: Annotated[AuthenticatedUser, Depends(require_permission("persona:create"))],
):
    try:
        return ResponseModel(data=await _get_service().upload_persona_image(file, user_id=user.user_id))
    except ApplicationError as error:
        set_error_response(response, error, http_request)
        message = render_error_message(error, locale=request_locale(http_request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
