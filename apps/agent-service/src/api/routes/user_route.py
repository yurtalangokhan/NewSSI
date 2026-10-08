"""
User project, file, and LLM provider routes.

Endpoints:
  User-related (projects, files) — stay in agent-service (coupled with chat/file infra).
  LLM provider endpoints — agent infrastructure.
"""

from typing import Annotated

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile

from api.dependencies import AuthenticatedUser, extract_auth_token_from_request, require_permission, require_user
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from schemas.common import SuccessResponse
from schemas.users import (
    AdminLlmProviderResponse,
    BuiltinLlmOptionResponse,
    DefaultAssistantResponse,
    FileStatusesPayload,
    MoveChatSessionPayload,
    OllamaModelSummaryResponse,
    PersonaProvidersResponse,
    ProjectFileItemResponse,
    ProjectInstructionsResponse,
    ProjectTokenCountResponse,
    ProviderConfigResponse,
    RecentFileResponse,
    RenameProjectPayload,
    UpsertProjectInstructionsPayload,
    UserProjectDetailResponse,
    UserProjectFileUploadResponse,
    UserProjectResponse,
)
from service.users import UserService, get_user_service

router = APIRouter(tags=["user"], dependencies=[Depends(require_user)])


def _get_service() -> UserService:
    return get_user_service()


async def _resolve_project_identity(request: Request, user: AuthenticatedUser) -> tuple[str, list[str]]:
    return await _get_service().resolve_project_identity(extract_auth_token_from_request(request), user)


@router.get("/api/user/files/recent", response_model=ResponseModel[list[RecentFileResponse]])
async def get_recent_files(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    try:
        effective_user_id, _ = await _resolve_project_identity(request, user)
        return ResponseModel[list[RecentFileResponse]](data=await _get_service().get_recent_files(effective_user_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/llm/provider", response_model=ResponseModel[ProviderConfigResponse])
async def get_llm_provider(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
):
    try:
        return ResponseModel[ProviderConfigResponse](data=await _get_service().get_llm_provider())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/admin/llm/built-in/options", response_model=ResponseModel[list[BuiltinLlmOptionResponse]])
async def get_llm_built_in_options(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
):
    try:
        return ResponseModel[list[BuiltinLlmOptionResponse]](data=await _get_service().get_llm_built_in_options())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/admin/llm/test/default", response_model=ResponseModel[SuccessResponse])
async def test_llm_default(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
):
    try:
        return ResponseModel[SuccessResponse](data=await _get_service().test_llm_default())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/admin/default-assistant", response_model=ResponseModel[DefaultAssistantResponse | None])
async def get_default_assistant(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("assistant:read"))],
):
    try:
        await _get_service().get_default_assistant()
        return ResponseModel[DefaultAssistantResponse | None](data=None)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/user/projects", response_model=ResponseModel[list[UserProjectResponse]])
async def get_user_projects(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    try:
        effective_user_id, owner_ids = await _resolve_project_identity(request, user)
        return ResponseModel[list[UserProjectResponse]](
            data=await _get_service().get_user_projects(effective_user_id, owner_ids)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/user/projects/create", response_model=ResponseModel[UserProjectResponse])
async def create_user_project(
    response: Response,
    request: Request,
    name: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:create"))],
):
    try:
        effective_user_id, _ = await _resolve_project_identity(request, user)
        return ResponseModel[UserProjectResponse](
            data=await _get_service().create_user_project(effective_user_id, name)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/user/projects/file/upload", response_model=ResponseModel[UserProjectFileUploadResponse])
async def upload_project_files(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:update"))],
    files: Annotated[list[UploadFile], File()],
    project_id: Annotated[int | None, Form()] = None,
    temp_id_map: Annotated[str | None, Form()] = None,
):
    try:
        effective_user_id, owner_ids = await _resolve_project_identity(request, user)
        return ResponseModel[UserProjectFileUploadResponse](
            data=await _get_service().upload_user_project_files(
                user_id=effective_user_id,
                files=files,
                project_id=project_id,
                temp_id_map_raw=temp_id_map,
                owner_ids=owner_ids,
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/user/projects/files/{project_id}", response_model=ResponseModel[list[ProjectFileItemResponse]])
async def get_files_in_project(
    response: Response,
    request: Request,
    project_id: int,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    try:
        effective_user_id, owner_ids = await _resolve_project_identity(request, user)
        return ResponseModel[list[ProjectFileItemResponse]](
            data=await _get_service().get_files_in_project(effective_user_id, project_id, owner_ids)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/user/projects/{project_id}/files/{file_id}", response_model=ResponseModel[SuccessResponse])
async def link_file_to_project(
    response: Response,
    request: Request,
    project_id: int,
    file_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:update"))],
):
    try:
        effective_user_id, owner_ids = await _resolve_project_identity(request, user)
        return ResponseModel[SuccessResponse](
            data=await _get_service().link_file_to_project(effective_user_id, project_id, file_id, owner_ids)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/api/user/projects/{project_id}/files/{file_id}", response_model=ResponseModel[SuccessResponse])
async def unlink_file_from_project(
    response: Response,
    request: Request,
    project_id: int,
    file_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:update"))],
):
    try:
        effective_user_id, _ = await _resolve_project_identity(request, user)
        return ResponseModel[SuccessResponse](
            data=await _get_service().unlink_file_from_project(effective_user_id, project_id, file_id)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/user/projects/file/{file_id}", response_model=ResponseModel[ProjectFileItemResponse])
async def get_user_file(
    response: Response,
    request: Request,
    file_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    try:
        effective_user_id, _ = await _resolve_project_identity(request, user)
        return ResponseModel[ProjectFileItemResponse](
            data=await _get_service().get_user_file(effective_user_id, file_id)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/api/user/projects/file/{file_id}", response_model=ResponseModel[SuccessResponse])
async def delete_user_file(
    response: Response,
    request: Request,
    file_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:delete"))],
):
    try:
        effective_user_id, _ = await _resolve_project_identity(request, user)
        return ResponseModel[SuccessResponse](data=await _get_service().delete_user_file(effective_user_id, file_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/user/projects/file/statuses", response_model=ResponseModel[list[ProjectFileItemResponse]])
async def get_user_file_statuses(
    response: Response,
    request: Request,
    payload: FileStatusesPayload,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    try:
        effective_user_id, _ = await _resolve_project_identity(request, user)
        return ResponseModel[list[ProjectFileItemResponse]](
            data=await _get_service().get_user_file_statuses(effective_user_id, payload.file_ids)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/user/projects/{project_id}", response_model=ResponseModel[UserProjectResponse])
async def get_user_project(
    response: Response,
    request: Request,
    project_id: int,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    try:
        effective_user_id, owner_ids = await _resolve_project_identity(request, user)
        return ResponseModel[UserProjectResponse](
            data=await _get_service().get_user_project(effective_user_id, project_id, owner_ids)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.patch("/api/user/projects/{project_id}", response_model=ResponseModel[UserProjectResponse])
async def rename_user_project(
    response: Response,
    request: Request,
    project_id: int,
    payload: RenameProjectPayload,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:update"))],
):
    try:
        effective_user_id, owner_ids = await _resolve_project_identity(request, user)
        return ResponseModel[UserProjectResponse](
            data=await _get_service().rename_user_project(effective_user_id, project_id, payload.name, owner_ids)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/api/user/projects/{project_id}", response_model=ResponseModel[SuccessResponse])
async def delete_user_project(
    response: Response,
    request: Request,
    project_id: int,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:delete"))],
):
    try:
        effective_user_id, owner_ids = await _resolve_project_identity(request, user)
        return ResponseModel[SuccessResponse](
            data=await _get_service().delete_user_project(effective_user_id, project_id, owner_ids)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/user/projects/{project_id}/details", response_model=ResponseModel[UserProjectDetailResponse])
async def get_user_project_details(
    response: Response,
    request: Request,
    project_id: int,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    try:
        effective_user_id, owner_ids = await _resolve_project_identity(request, user)
        return ResponseModel[UserProjectDetailResponse](
            data=await _get_service().get_user_project_details(effective_user_id, project_id, owner_ids)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/user/projects/{project_id}/instructions", response_model=ResponseModel[ProjectInstructionsResponse])
async def get_user_project_instructions(
    response: Response,
    request: Request,
    project_id: int,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    try:
        effective_user_id, owner_ids = await _resolve_project_identity(request, user)
        return ResponseModel[ProjectInstructionsResponse](
            data=await _get_service().get_user_project_instructions(effective_user_id, project_id, owner_ids)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/user/projects/{project_id}/instructions", response_model=ResponseModel[ProjectInstructionsResponse])
async def upsert_user_project_instructions(
    response: Response,
    request: Request,
    project_id: int,
    payload: UpsertProjectInstructionsPayload,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:update"))],
):
    try:
        effective_user_id, owner_ids = await _resolve_project_identity(request, user)
        return ResponseModel[ProjectInstructionsResponse](
            data=await _get_service().upsert_user_project_instructions(
                effective_user_id, project_id, payload.instructions, owner_ids
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/user/projects/{project_id}/token-count", response_model=ResponseModel[ProjectTokenCountResponse])
async def get_project_token_count(
    response: Response,
    request: Request,
    project_id: int,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    try:
        effective_user_id, _ = await _resolve_project_identity(request, user)
        return ResponseModel[ProjectTokenCountResponse](
            data=await _get_service().get_project_token_count(effective_user_id, project_id)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/user/projects/{project_id}/move_chat_session", response_model=ResponseModel[SuccessResponse])
async def move_chat_session_to_project(
    response: Response,
    request: Request,
    project_id: int,
    payload: MoveChatSessionPayload,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:update"))],
):
    try:
        effective_user_id, owner_ids = await _resolve_project_identity(request, user)
        return ResponseModel[SuccessResponse](
            data=await _get_service().move_chat_session_to_project(
                user_id=effective_user_id,
                project_id=project_id,
                chat_session_id=payload.chat_session_id,
                owner_ids=owner_ids,
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/user/projects/remove_chat_session", response_model=ResponseModel[SuccessResponse])
async def remove_chat_session_from_project(
    response: Response,
    request: Request,
    payload: MoveChatSessionPayload,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:update"))],
):
    try:
        effective_user_id, owner_ids = await _resolve_project_identity(request, user)
        return ResponseModel[SuccessResponse](
            data=await _get_service().remove_chat_session_from_project(
                user_id=effective_user_id, chat_session_id=payload.chat_session_id, owner_ids=owner_ids
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/admin/llm/provider", response_model=ResponseModel[AdminLlmProviderResponse])
async def get_admin_llm_provider(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
):
    try:
        return ResponseModel[AdminLlmProviderResponse](data=await _get_service().get_admin_llm_provider())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/admin/llm/test", response_model=ResponseModel[SuccessResponse])
async def test_llm(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
):
    try:
        return ResponseModel[SuccessResponse](data=await _get_service().test_llm())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/admin/llm/default", response_model=ResponseModel[SuccessResponse])
async def set_default_llm(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:update"))],
):
    try:
        return ResponseModel[SuccessResponse](data=await _get_service().set_default_llm())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/admin/llm/ollama/available-models", response_model=ResponseModel[list[OllamaModelSummaryResponse]])
async def get_ollama_models(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
):
    try:
        return ResponseModel[list[OllamaModelSummaryResponse]](data=await _get_service().get_ollama_models())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.put("/api/admin/llm/provider", response_model=ResponseModel[SuccessResponse])
async def save_llm_provider(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:update"))],
):
    try:
        return ResponseModel[SuccessResponse](data=await _get_service().save_llm_provider())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/admin/llm/provider", response_model=ResponseModel[SuccessResponse])
async def create_llm_provider(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:create"))],
):
    try:
        return ResponseModel[SuccessResponse](data=await _get_service().create_llm_provider())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/llm/persona/{persona_id}/providers", response_model=ResponseModel[PersonaProvidersResponse])
async def get_persona_providers(
    request: Request,
    response: Response,
    persona_id: int,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
):
    try:
        return ResponseModel[PersonaProvidersResponse](data=await _get_service().get_persona_providers(persona_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
