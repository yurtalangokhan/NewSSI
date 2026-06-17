"""
User preferences and settings routes.

Endpoints: /api/user/*, /api/llm/*, /admin/llm/*
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
from pydantic import BaseModel

from api.dependencies import AuthenticatedUser, require_user
from controller import UserController, get_user_controller
from service.AuthService import get_auth_service

router = APIRouter(tags=["user"], dependencies=[Depends(require_user)])


def _get_controller() -> UserController:
    return get_user_controller()


async def _resolve_project_identity(
    request: Request,
    user: AuthenticatedUser,
) -> tuple[str, list[str]]:
    controller = _get_controller()
    identity = await get_auth_service().resolve_user_identity(request=request, user_id=user.user_id)
    primary_user_id = str(identity.get("primary_user_id") or user.user_id)
    effective_user_id = await controller.resolve_projects_user_id(primary_user_id)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    owner_ids: list[str] = []
    for candidate in [effective_user_id, *(identity.get("known_user_ids") or []), user.user_id]:
        if not candidate:
            continue
        candidate_id = str(candidate)
        if candidate_id not in owner_ids:
            owner_ids.append(candidate_id)

    return effective_user_id, owner_ids


class PinnedAssistantsUpdate(BaseModel):
    ordered_assistant_ids: list[int] = []


class UserPersonalizationPayload(BaseModel):
    name: str | None = None
    role: str | None = None
    long_term_memory_enabled: bool | None = None
    extract_memory: bool | None = None
    user_preferences: str | None = None


class ThemePreferencePayload(BaseModel):
    theme_preference: str


class ChatBackgroundPayload(BaseModel):
    chat_background: str | None = None


class DefaultModelPayload(BaseModel):
    default_model: str | None = None
    default_provider_id: str | None = None


class AutoScrollPayload(BaseModel):
    auto_scroll: bool


class DefaultAppModePayload(BaseModel):
    default_app_mode: str


class InputPromptPayload(BaseModel):
    prompt: str
    content: str
    active: bool = True
    is_public: bool = False


class RenameProjectPayload(BaseModel):
    name: str


class UpsertProjectInstructionsPayload(BaseModel):
    instructions: str


class MoveChatSessionPayload(BaseModel):
    chat_session_id: str


class FileStatusesPayload(BaseModel):
    file_ids: list[str]


@router.get("/api/user/assistant/preferences")
async def get_user_assistant_preferences():
    return await _get_controller().get_user_assistant_preferences()


@router.get("/api/user/files/recent")
async def get_recent_files(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    effective_user_id, _ = await _resolve_project_identity(request, user)
    return await _get_controller().get_recent_files(effective_user_id)


@router.patch("/api/user/pinned-assistants")
async def update_pinned_assistants(request: Request, update: PinnedAssistantsUpdate):
    _ = request
    return await _get_controller().update_pinned_assistants(update.ordered_assistant_ids)


@router.get("/api/user/pinned-assistants")
async def get_pinned_assistants():
    return await _get_controller().get_pinned_assistants()


@router.patch("/api/user/personalization")
async def update_user_personalization(
    payload: UserPersonalizationPayload,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    return await _get_controller().update_user_personalization(
        user_id=user.user_id,
        personalization=payload.model_dump(exclude_none=True),
    )


@router.patch("/api/user/theme-preference")
async def update_user_theme_preference(
    payload: ThemePreferencePayload,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    return await _get_controller().update_user_theme_preference(
        user_id=user.user_id,
        theme_preference=payload.theme_preference,
    )


@router.patch("/api/user/chat-background")
async def update_user_chat_background(
    payload: ChatBackgroundPayload,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    return await _get_controller().update_user_chat_background(
        user_id=user.user_id,
        chat_background=payload.chat_background,
    )


@router.patch("/api/user/default-model")
async def update_user_default_model(
    payload: DefaultModelPayload,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    return await _get_controller().update_user_default_model(
        user_id=user.user_id,
        default_model=payload.default_model,
        default_provider_id=payload.default_provider_id,
    )


@router.patch("/api/auto-scroll")
async def update_user_auto_scroll(
    payload: AutoScrollPayload,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    return await _get_controller().update_user_auto_scroll(
        user_id=user.user_id,
        auto_scroll=payload.auto_scroll,
    )


@router.patch("/api/shortcut-enabled")
async def update_user_shortcut_enabled(
    shortcut_enabled: bool,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    return await _get_controller().update_user_shortcut_enabled(
        user_id=user.user_id,
        shortcut_enabled=shortcut_enabled,
    )


@router.patch("/api/user/default-app-mode")
async def update_user_default_app_mode(
    payload: DefaultAppModePayload,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    return await _get_controller().update_user_default_app_mode(
        user_id=user.user_id,
        default_app_mode=payload.default_app_mode,
    )


@router.get("/api/llm/persona/{persona_id}/providers")
async def get_persona_llm_providers(persona_id: int):
    return await _get_controller().get_persona_providers(persona_id)


@router.get("/api/llm/provider")
async def get_llm_provider():
    return await _get_controller().get_llm_provider()


@router.get("/api/admin/llm/built-in/options")
async def get_llm_built_in_options():
    return await _get_controller().get_llm_built_in_options()


@router.post("/api/admin/llm/test/default")
async def test_llm_default():
    return await _get_controller().test_llm_default()


@router.get("/api/admin/default-assistant")
async def get_default_assistant():
    return await _get_controller().get_default_assistant()


@router.get("/api/user/projects")
async def get_user_projects(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    effective_user_id, owner_ids = await _resolve_project_identity(request, user)
    return await _get_controller().get_user_projects(effective_user_id, owner_ids)


@router.post("/api/user/projects/create")
async def create_user_project(
    request: Request,
    name: str,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    effective_user_id, _ = await _resolve_project_identity(request, user)
    return await _get_controller().create_user_project(effective_user_id, name)


@router.post("/api/user/projects/file/upload")
async def upload_project_files(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
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
    user: Annotated[AuthenticatedUser, Depends(require_user)],
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
    user: Annotated[AuthenticatedUser, Depends(require_user)],
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
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    effective_user_id, _ = await _resolve_project_identity(request, user)
    return await _get_controller().unlink_file_from_project(effective_user_id, project_id, file_id)


@router.get("/api/user/projects/file/{file_id}")
async def get_user_file(
    request: Request,
    file_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    effective_user_id, _ = await _resolve_project_identity(request, user)
    return await _get_controller().get_user_file(effective_user_id, file_id)


@router.delete("/api/user/projects/file/{file_id}")
async def delete_user_file(
    request: Request,
    file_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    effective_user_id, _ = await _resolve_project_identity(request, user)
    return await _get_controller().delete_user_file(effective_user_id, file_id)


@router.post("/api/user/projects/file/statuses")
async def get_user_file_statuses(
    request: Request,
    payload: FileStatusesPayload,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    effective_user_id, _ = await _resolve_project_identity(request, user)
    return await _get_controller().get_user_file_statuses(effective_user_id, payload.file_ids)


@router.get("/api/user/projects/{project_id}")
async def get_user_project(
    request: Request,
    project_id: int,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    effective_user_id, owner_ids = await _resolve_project_identity(request, user)
    return await _get_controller().get_user_project(effective_user_id, project_id, owner_ids)


@router.patch("/api/user/projects/{project_id}")
async def rename_user_project(
    request: Request,
    project_id: int,
    payload: RenameProjectPayload,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
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
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    effective_user_id, owner_ids = await _resolve_project_identity(request, user)
    return await _get_controller().delete_user_project(effective_user_id, project_id, owner_ids)


@router.get("/api/user/projects/{project_id}/details")
async def get_user_project_details(
    request: Request,
    project_id: int,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
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
    user: Annotated[AuthenticatedUser, Depends(require_user)],
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
    user: Annotated[AuthenticatedUser, Depends(require_user)],
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
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    effective_user_id, _ = await _resolve_project_identity(request, user)
    return await _get_controller().get_project_token_count(effective_user_id, project_id)


@router.post("/api/user/projects/{project_id}/move_chat_session")
async def move_chat_session_to_project(
    request: Request,
    project_id: int,
    payload: MoveChatSessionPayload,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
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
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    effective_user_id, owner_ids = await _resolve_project_identity(request, user)
    return await _get_controller().remove_chat_session_from_project(
        user_id=effective_user_id,
        chat_session_id=payload.chat_session_id,
        owner_ids=owner_ids,
    )


@router.get("/api/notifications")
async def get_notifications():
    return await _get_controller().get_notifications()


@router.get("/api/input_prompt")
async def get_input_prompts(user: Annotated[AuthenticatedUser, Depends(require_user)]):
    return await _get_controller().get_input_prompts(user.user_id)


@router.post("/api/input_prompt")
async def create_input_prompt(
    payload: InputPromptPayload,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    return await _get_controller().create_input_prompt(
        user_id=user.user_id,
        payload=payload.model_dump(),
    )


@router.patch("/api/input_prompt/{prompt_id}")
async def update_input_prompt(
    prompt_id: int,
    payload: InputPromptPayload,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    return await _get_controller().update_input_prompt(
        user_id=user.user_id,
        prompt_id=prompt_id,
        payload=payload.model_dump(),
    )


@router.delete("/api/input_prompt/{prompt_id}")
async def delete_input_prompt(
    prompt_id: int,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    return await _get_controller().delete_input_prompt(user_id=user.user_id, prompt_id=prompt_id)


@router.get("/api/manage/connector-status")
async def get_connector_status():
    return await _get_controller().get_connector_status()


@router.get("/api/federated/oauth-status")
async def get_federated_oauth_status():
    return await _get_controller().get_federated_oauth_status()


@router.get("/api/manage/admin/valid-domains")
async def get_valid_domains():
    return await _get_controller().get_valid_domains()


@router.get("/api/federated")
async def get_federated():
    return await _get_controller().get_federated()


@router.get("/api/query/valid-tags")
async def get_valid_tags():
    return await _get_controller().get_valid_tags()


@router.get("/api/manage/document-set")
async def get_document_sets():
    return await _get_controller().get_document_sets()


@router.get("/admin/llm/provider")
async def get_admin_llm_provider():
    return await _get_controller().get_admin_llm_provider()


@router.post("/api/admin/llm/test")
async def test_llm():
    return await _get_controller().test_llm()


@router.post("/api/admin/llm/default")
async def set_default_llm():
    return await _get_controller().set_default_llm()


@router.get("/api/admin/llm/ollama/available-models")
async def get_ollama_models():
    return await _get_controller().get_ollama_models()


@router.put("/api/admin/llm/provider")
async def save_llm_provider():
    return await _get_controller().save_llm_provider()


@router.post("/api/admin/llm/provider")
async def create_llm_provider():
    return await _get_controller().create_llm_provider()


@router.get("/llm/persona/{persona_id}/providers")
async def get_persona_providers(persona_id: int):
    return await _get_controller().get_persona_providers(persona_id)
