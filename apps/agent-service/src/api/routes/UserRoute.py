"""
User project, file, and LLM provider routes.

Endpoints:
  User-related (projects, files) — stay in agent-service (coupled with chat/file infra).
  LLM provider endpoints — agent infrastructure.
"""

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from i18n import t

from api.dependencies import (
    AuthenticatedUser,
    extract_auth_token_from_request,
    require_permission,
    require_user,
)
from controller import UserController, get_user_controller
from models.users import (
    FileStatusesPayload,
    MoveChatSessionPayload,
    RenameProjectPayload,
    UpsertProjectInstructionsPayload,
)
from service.AuthService import get_auth_service

router = APIRouter(tags=["user"], dependencies=[Depends(require_user)])


def _get_controller() -> UserController:
    return get_user_controller()


async def _resolve_project_identity(
    request: Request,
    user: AuthenticatedUser,
) -> tuple[str, list[str]]:
    controller = _get_controller()
    identity = await get_auth_service().resolve_user_identity(
        token=extract_auth_token_from_request(request),
        user_id=user.user_id,
        user=user,
    )
    primary_user_id = str(identity.get("primary_user_id") or user.user_id)
    effective_user_id = await controller.resolve_projects_user_id(primary_user_id)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail=t("auth.not_authenticated"))

    owner_ids: list[str] = []
    for candidate in [effective_user_id, *(identity.get("known_user_ids") or []), user.user_id]:
        if not candidate:
            continue
        candidate_id = str(candidate)
        if candidate_id not in owner_ids:
            owner_ids.append(candidate_id)

    return effective_user_id, owner_ids


@router.get("/api/user/files/recent")
async def get_recent_files(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    effective_user_id, _ = await _resolve_project_identity(request, user)
    return await _get_controller().get_recent_files(effective_user_id)


@router.get("/api/llm/persona/{persona_id}/providers")
async def get_persona_llm_providers(
    persona_id: int,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
):
    return await _get_controller().get_persona_providers(persona_id)


@router.get("/api/llm/provider")
async def get_llm_provider(
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
):
    return await _get_controller().get_llm_provider()


@router.get("/api/admin/llm/built-in/options")
async def get_llm_built_in_options(
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
):
    return await _get_controller().get_llm_built_in_options()


@router.post("/api/admin/llm/test/default")
async def test_llm_default(
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
):
    return await _get_controller().test_llm_default()


@router.get("/api/admin/default-assistant")
async def get_default_assistant(
    _user: Annotated[AuthenticatedUser, Depends(require_permission("assistant:read"))],
):
    return await _get_controller().get_default_assistant()


@router.get("/api/user/projects")
async def get_user_projects(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    effective_user_id, owner_ids = await _resolve_project_identity(request, user)
    return await _get_controller().get_user_projects(effective_user_id, owner_ids)


@router.post("/api/user/projects/create")
async def create_user_project(
    request: Request,
    name: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:create"))],
):
    effective_user_id, _ = await _resolve_project_identity(request, user)
    return await _get_controller().create_user_project(effective_user_id, name)


@router.post("/api/user/projects/file/upload")
async def upload_project_files(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:update"))],
    files: list[UploadFile] = File(...),
    project_id: int | None = Form(default=None),
    temp_id_map: str | None = Form(default=None),
):
    effective_user_id, owner_ids = await _resolve_project_identity(request, user)
    return await _get_controller().upload_user_project_files(
        user_id=effective_user_id,
        files=files,
        project_id=project_id,
        temp_id_map_raw=temp_id_map,
        owner_ids=owner_ids,
    )


@router.get("/api/user/projects/files/{project_id}")
async def get_files_in_project(
    request: Request,
    project_id: int,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    effective_user_id, owner_ids = await _resolve_project_identity(request, user)
    return await _get_controller().get_files_in_project(
        effective_user_id,
        project_id,
        owner_ids,
    )


@router.post("/api/user/projects/{project_id}/files/{file_id}")
async def link_file_to_project(
    request: Request,
    project_id: int,
    file_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:update"))],
):
    effective_user_id, owner_ids = await _resolve_project_identity(request, user)
    return await _get_controller().link_file_to_project(
        effective_user_id,
        project_id,
        file_id,
        owner_ids,
    )


@router.delete("/api/user/projects/{project_id}/files/{file_id}")
async def unlink_file_from_project(
    request: Request,
    project_id: int,
    file_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:update"))],
):
    effective_user_id, _ = await _resolve_project_identity(request, user)
    return await _get_controller().unlink_file_from_project(effective_user_id, project_id, file_id)


@router.get("/api/user/projects/file/{file_id}")
async def get_user_file(
    request: Request,
    file_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    effective_user_id, _ = await _resolve_project_identity(request, user)
    return await _get_controller().get_user_file(effective_user_id, file_id)


@router.delete("/api/user/projects/file/{file_id}")
async def delete_user_file(
    request: Request,
    file_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:delete"))],
):
    effective_user_id, _ = await _resolve_project_identity(request, user)
    return await _get_controller().delete_user_file(effective_user_id, file_id)


@router.post("/api/user/projects/file/statuses")
async def get_user_file_statuses(
    request: Request,
    payload: FileStatusesPayload,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    effective_user_id, _ = await _resolve_project_identity(request, user)
    return await _get_controller().get_user_file_statuses(effective_user_id, payload.file_ids)


@router.get("/api/user/projects/{project_id}")
async def get_user_project(
    request: Request,
    project_id: int,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    effective_user_id, owner_ids = await _resolve_project_identity(request, user)
    return await _get_controller().get_user_project(effective_user_id, project_id, owner_ids)


@router.patch("/api/user/projects/{project_id}")
async def rename_user_project(
    request: Request,
    project_id: int,
    payload: RenameProjectPayload,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:update"))],
):
    effective_user_id, owner_ids = await _resolve_project_identity(request, user)
    return await _get_controller().rename_user_project(
        effective_user_id,
        project_id,
        payload.name,
        owner_ids,
    )


@router.delete("/api/user/projects/{project_id}")
async def delete_user_project(
    request: Request,
    project_id: int,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:delete"))],
):
    effective_user_id, owner_ids = await _resolve_project_identity(request, user)
    return await _get_controller().delete_user_project(effective_user_id, project_id, owner_ids)


@router.get("/api/user/projects/{project_id}/details")
async def get_user_project_details(
    request: Request,
    project_id: int,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    effective_user_id, owner_ids = await _resolve_project_identity(request, user)
    return await _get_controller().get_user_project_details(
        effective_user_id,
        project_id,
        owner_ids,
    )


@router.get("/api/user/projects/{project_id}/instructions")
async def get_user_project_instructions(
    request: Request,
    project_id: int,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    effective_user_id, owner_ids = await _resolve_project_identity(request, user)
    return await _get_controller().get_user_project_instructions(
        effective_user_id,
        project_id,
        owner_ids,
    )


@router.post("/api/user/projects/{project_id}/instructions")
async def upsert_user_project_instructions(
    request: Request,
    project_id: int,
    payload: UpsertProjectInstructionsPayload,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:update"))],
):
    effective_user_id, owner_ids = await _resolve_project_identity(request, user)
    return await _get_controller().upsert_user_project_instructions(
        effective_user_id,
        project_id,
        payload.instructions,
        owner_ids,
    )


@router.get("/api/user/projects/{project_id}/token-count")
async def get_project_token_count(
    request: Request,
    project_id: int,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:read"))],
):
    effective_user_id, _ = await _resolve_project_identity(request, user)
    return await _get_controller().get_project_token_count(effective_user_id, project_id)


@router.post("/api/user/projects/{project_id}/move_chat_session")
async def move_chat_session_to_project(
    request: Request,
    project_id: int,
    payload: MoveChatSessionPayload,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:update"))],
):
    effective_user_id, owner_ids = await _resolve_project_identity(request, user)
    return await _get_controller().move_chat_session_to_project(
        user_id=effective_user_id,
        project_id=project_id,
        chat_session_id=payload.chat_session_id,
        owner_ids=owner_ids,
    )


@router.post("/api/user/projects/remove_chat_session")
async def remove_chat_session_from_project(
    request: Request,
    payload: MoveChatSessionPayload,
    user: Annotated[AuthenticatedUser, Depends(require_permission("project:update"))],
):
    effective_user_id, owner_ids = await _resolve_project_identity(request, user)
    return await _get_controller().remove_chat_session_from_project(
        user_id=effective_user_id,
        chat_session_id=payload.chat_session_id,
        owner_ids=owner_ids,
    )


@router.get("/admin/llm/provider")
async def get_admin_llm_provider(
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
):
    return await _get_controller().get_admin_llm_provider()


@router.post("/api/admin/llm/test")
async def test_llm(
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
):
    return await _get_controller().test_llm()


@router.post("/api/admin/llm/default")
async def set_default_llm(
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:update"))],
):
    return await _get_controller().set_default_llm()


@router.get("/api/admin/llm/ollama/available-models")
async def get_ollama_models(
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
):
    return await _get_controller().get_ollama_models()


@router.put("/api/admin/llm/provider")
async def save_llm_provider(
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:update"))],
):
    return await _get_controller().save_llm_provider()


@router.post("/api/admin/llm/provider")
async def create_llm_provider(
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:create"))],
):
    return await _get_controller().create_llm_provider()


@router.get("/llm/persona/{persona_id}/providers")
async def get_persona_providers(
    persona_id: int,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
):
    return await _get_controller().get_persona_providers(persona_id)
