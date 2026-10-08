"""Provider management API routes."""

from __future__ import annotations

from typing import Annotated

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse

from api.dependencies import AuthenticatedUser, require_permission, require_user
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from schemas.common import SuccessResponse
from schemas.providers import (
    AllProvidersResponse,
    AvailableModelResponse,
    DefaultModelPayload,
    OllamaPullPayload,
    ProviderModelResponse,
    ProviderResponse,
    ReorderPayload,
    TestConnectionPayload,
    TestConnectionResponse,
    UrlProviderPayload,
    UserProviderPayload,
    UserProviderResponse,
    UserProviderUpdatePayload,
    WellKnownProviderResponse,
)
from service.model_providers import provider_application_service as application_service
from service.model_providers.model_provider_service import ProviderService
from service.stream.error_events import guard_stream

router = APIRouter(prefix="/api/admin", tags=["providers"], dependencies=[Depends(require_user)])
_svc = ProviderService()


@router.get("/providers", response_model=ResponseModel[AllProvidersResponse])
async def list_providers(
    request: Request,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
) -> ResponseModel[AllProvidersResponse]:
    try:
        return ResponseModel[AllProvidersResponse](data=await application_service.list_providers(user_id=user.user_id))
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/providers/available-models", response_model=ResponseModel[list[AvailableModelResponse]])
async def get_available_models(
    request: Request,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
) -> ResponseModel[list[AvailableModelResponse]]:
    try:
        return ResponseModel[list[AvailableModelResponse]](
            data=await application_service.get_available_models(user_id=user.user_id)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/providers", response_model=ResponseModel[ProviderResponse])
async def create_provider(
    request: Request,
    response: Response,
    body: UrlProviderPayload,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:create"))],
) -> ResponseModel[ProviderResponse]:
    try:
        return ResponseModel[ProviderResponse](
            data=await application_service.create_provider(user_id=user.user_id, body=body)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.put("/providers/order", response_model=ResponseModel[SuccessResponse])
async def reorder_providers(
    request: Request,
    response: Response,
    body: ReorderPayload,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:update"))],
) -> ResponseModel[SuccessResponse]:
    try:
        return ResponseModel[SuccessResponse](
            data=await application_service.reorder_providers(user_id=user.user_id, body=body)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.put("/providers/{provider_id}", response_model=ResponseModel[ProviderResponse])
async def update_provider(
    request: Request,
    response: Response,
    provider_id: str,
    body: UrlProviderPayload,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:update"))],
) -> ResponseModel[ProviderResponse]:
    try:
        return ResponseModel[ProviderResponse](
            data=await application_service.update_provider(user_id=user.user_id, provider_id=provider_id, body=body)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/providers/{provider_id}", response_model=ResponseModel[SuccessResponse])
async def delete_provider(
    request: Request,
    response: Response,
    provider_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:delete"))],
) -> ResponseModel[SuccessResponse]:
    try:
        return ResponseModel[SuccessResponse](
            data=await application_service.delete_provider(user_id=user.user_id, provider_id=provider_id)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.patch("/providers/{config_id}/default-model", response_model=ResponseModel[SuccessResponse])
async def update_default_model(
    request: Request,
    response: Response,
    config_id: str,
    body: DefaultModelPayload,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:update"))],
) -> ResponseModel[SuccessResponse]:
    try:
        return ResponseModel[SuccessResponse](
            data=await application_service.update_default_model(user_id=user.user_id, config_id=config_id, body=body)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/user-providers", response_model=ResponseModel[UserProviderResponse])
async def create_user_provider(
    request: Request,
    response: Response,
    body: UserProviderPayload,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:create"))],
) -> ResponseModel[UserProviderResponse]:
    try:
        return ResponseModel[UserProviderResponse](
            data=await application_service.create_user_provider(user_id=user.user_id, body=body)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.put("/user-providers/{provider_id}", response_model=ResponseModel[UserProviderResponse])
async def update_user_provider(
    request: Request,
    response: Response,
    provider_id: str,
    body: UserProviderUpdatePayload,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:update"))],
) -> ResponseModel[UserProviderResponse]:
    try:
        return ResponseModel[UserProviderResponse](
            data=await application_service.update_user_provider(
                user_id=user.user_id, provider_id=provider_id, body=body
            )
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/user-providers/{provider_id}", response_model=ResponseModel[SuccessResponse])
async def delete_user_provider(
    request: Request,
    response: Response,
    provider_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:delete"))],
) -> ResponseModel[SuccessResponse]:
    try:
        return ResponseModel[SuccessResponse](
            data=await application_service.delete_user_provider(user_id=user.user_id, provider_id=provider_id)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/providers/well-known", response_model=ResponseModel[list[WellKnownProviderResponse]])
async def get_well_known_providers(
    request: Request, response: Response
) -> ResponseModel[list[WellKnownProviderResponse]]:
    try:
        return ResponseModel[list[WellKnownProviderResponse]](data=await application_service.get_well_known_providers())
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/providers/test-connection", response_model=ResponseModel[TestConnectionResponse])
async def test_provider_connection(
    request: Request,
    response: Response,
    body: TestConnectionPayload,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
) -> ResponseModel[TestConnectionResponse]:
    try:
        return ResponseModel[TestConnectionResponse](
            data=await application_service.test_provider_connection(user_id=user.user_id, body=body)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/providers/{provider_id}/models", response_model=ResponseModel[list[ProviderModelResponse]])
async def get_provider_models(
    request: Request,
    response: Response,
    provider_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
) -> ResponseModel[list[ProviderModelResponse]]:
    try:
        return ResponseModel[list[ProviderModelResponse]](
            data=await application_service.get_provider_models(user_id=user.user_id, provider_id=provider_id)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/providers/{provider_id}/sync-models", response_model=ResponseModel[ProviderResponse])
async def sync_provider_models(
    request: Request,
    response: Response,
    provider_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:update"))],
) -> ResponseModel[ProviderResponse]:
    try:
        return ResponseModel[ProviderResponse](
            data=await application_service.sync_provider_models(user_id=user.user_id, provider_id=provider_id)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post(
    "/ollama/pull",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
            "description": "Stream of Ollama pull progress events (SSE)",
        }
    },
)
async def pull_ollama_model(
    body: OllamaPullPayload, user: Annotated[AuthenticatedUser, Depends(require_permission("provider:update"))]
):
    return StreamingResponse(
        guard_stream(_svc.stream_ollama_pull(body.model, body.provider_id, user.user_id)),
        media_type="text/event-stream",
    )


@router.get("/vllm/models", response_model=ResponseModel[list[AvailableModelResponse]])
async def get_vllm_models(
    request: Request,
    response: Response,
    provider_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
) -> ResponseModel[list[AvailableModelResponse]]:
    try:
        return ResponseModel[list[AvailableModelResponse]](
            data=await application_service.get_vllm_models(user_id=user.user_id, provider_id=provider_id)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
