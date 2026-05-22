"""
User preferences and settings routes.

Endpoints: /api/user/*, /api/llm/*, /admin/llm/*
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from api.dependencies import verify_api_key
from controller import UserController, get_user_controller

router = APIRouter(tags=["user"])


def _get_controller() -> UserController:
    return get_user_controller()


class PinnedAssistantsUpdate(BaseModel):
    ordered_assistant_ids: list[int] = []


class UserEmailPayload(BaseModel):
    user_email: str


class SetUserRolePayload(BaseModel):
    user_email: str
    new_role: str


class BulkInvitePayload(BaseModel):
    emails: list[str]


class CreateUserPayload(BaseModel):
    email: str
    role: str = "basic"
    first_name: str | None = None
    last_name: str | None = None
    password: str | None = None


class UpdateUserProfilePayload(BaseModel):
    user_email: str
    first_name: str | None = None
    last_name: str | None = None


class SetUserPasswordPayload(BaseModel):
    user_email: str
    password: str
    temporary: bool = False


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


@router.get("/api/user/assistant/preferences")
async def get_user_assistant_preferences():
    return await _get_controller().get_user_assistant_preferences()


@router.get("/api/user/files/recent")
async def get_recent_files():
    return await _get_controller().get_recent_files()


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
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        return {"success": False, "detail": "Not authenticated"}
    return await _get_controller().update_user_personalization(
        user_id=user_id,
        personalization=payload.model_dump(exclude_none=True),
    )


@router.patch("/api/user/theme-preference")
async def update_user_theme_preference(
    payload: ThemePreferencePayload,
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        return {"success": False, "detail": "Not authenticated"}
    return await _get_controller().update_user_theme_preference(
        user_id=user_id,
        theme_preference=payload.theme_preference,
    )


@router.patch("/api/user/chat-background")
async def update_user_chat_background(
    payload: ChatBackgroundPayload,
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        return {"success": False, "detail": "Not authenticated"}
    return await _get_controller().update_user_chat_background(
        user_id=user_id,
        chat_background=payload.chat_background,
    )


@router.patch("/api/user/default-model")
async def update_user_default_model(
    payload: DefaultModelPayload,
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        return {"success": False, "detail": "Not authenticated"}
    return await _get_controller().update_user_default_model(
        user_id=user_id,
        default_model=payload.default_model,
        default_provider_id=payload.default_provider_id,
    )


@router.patch("/api/auto-scroll")
async def update_user_auto_scroll(
    payload: AutoScrollPayload,
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        return {"success": False, "detail": "Not authenticated"}
    return await _get_controller().update_user_auto_scroll(
        user_id=user_id,
        auto_scroll=payload.auto_scroll,
    )


@router.patch("/api/shortcut-enabled")
async def update_user_shortcut_enabled(
    shortcut_enabled: bool,
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        return {"success": False, "detail": "Not authenticated"}
    return await _get_controller().update_user_shortcut_enabled(
        user_id=user_id,
        shortcut_enabled=shortcut_enabled,
    )


@router.patch("/api/user/default-app-mode")
async def update_user_default_app_mode(
    payload: DefaultAppModePayload,
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        return {"success": False, "detail": "Not authenticated"}
    return await _get_controller().update_user_default_app_mode(
        user_id=user_id,
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
async def get_user_projects(user_id: str | None = Depends(verify_api_key)):
    effective_user_id = await _get_controller().resolve_projects_user_id(user_id)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await _get_controller().get_user_projects(effective_user_id)


@router.post("/api/user/projects/create")
async def create_user_project(
    name: str,
    user_id: str | None = Depends(verify_api_key),
):
    effective_user_id = await _get_controller().resolve_projects_user_id(user_id)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await _get_controller().create_user_project(effective_user_id, name)


@router.get("/api/user/projects/{project_id}")
async def get_user_project(
    project_id: int,
    user_id: str | None = Depends(verify_api_key),
):
    effective_user_id = await _get_controller().resolve_projects_user_id(user_id)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await _get_controller().get_user_project(effective_user_id, project_id)


@router.patch("/api/user/projects/{project_id}")
async def rename_user_project(
    project_id: int,
    payload: RenameProjectPayload,
    user_id: str | None = Depends(verify_api_key),
):
    effective_user_id = await _get_controller().resolve_projects_user_id(user_id)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await _get_controller().rename_user_project(
        effective_user_id,
        project_id,
        payload.name,
    )


@router.delete("/api/user/projects/{project_id}")
async def delete_user_project(
    project_id: int,
    user_id: str | None = Depends(verify_api_key),
):
    effective_user_id = await _get_controller().resolve_projects_user_id(user_id)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await _get_controller().delete_user_project(effective_user_id, project_id)


@router.get("/api/user/projects/{project_id}/details")
async def get_user_project_details(
    project_id: int,
    user_id: str | None = Depends(verify_api_key),
):
    effective_user_id = await _get_controller().resolve_projects_user_id(user_id)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await _get_controller().get_user_project_details(effective_user_id, project_id)


@router.get("/api/user/projects/{project_id}/instructions")
async def get_user_project_instructions(
    project_id: int,
    user_id: str | None = Depends(verify_api_key),
):
    effective_user_id = await _get_controller().resolve_projects_user_id(user_id)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await _get_controller().get_user_project_instructions(effective_user_id, project_id)


@router.post("/api/user/projects/{project_id}/instructions")
async def upsert_user_project_instructions(
    project_id: int,
    payload: UpsertProjectInstructionsPayload,
    user_id: str | None = Depends(verify_api_key),
):
    effective_user_id = await _get_controller().resolve_projects_user_id(user_id)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await _get_controller().upsert_user_project_instructions(
        effective_user_id,
        project_id,
        payload.instructions,
    )


@router.get("/api/user/projects/{project_id}/token-count")
async def get_project_token_count(
    project_id: int,
    user_id: str | None = Depends(verify_api_key),
):
    effective_user_id = await _get_controller().resolve_projects_user_id(user_id)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await _get_controller().get_project_token_count(effective_user_id, project_id)


@router.post("/api/user/projects/{project_id}/move_chat_session")
async def move_chat_session_to_project(
    project_id: int,
    payload: MoveChatSessionPayload,
    user_id: str | None = Depends(verify_api_key),
):
    effective_user_id = await _get_controller().resolve_projects_user_id(user_id)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await _get_controller().move_chat_session_to_project(
        user_id=effective_user_id,
        project_id=project_id,
        chat_session_id=payload.chat_session_id,
    )


@router.post("/api/user/projects/remove_chat_session")
async def remove_chat_session_from_project(
    payload: MoveChatSessionPayload,
    user_id: str | None = Depends(verify_api_key),
):
    effective_user_id = await _get_controller().resolve_projects_user_id(user_id)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await _get_controller().remove_chat_session_from_project(
        user_id=effective_user_id,
        chat_session_id=payload.chat_session_id,
    )


@router.get("/api/notifications")
async def get_notifications():
    return await _get_controller().get_notifications()


@router.get("/api/input_prompt")
async def get_input_prompts(user_id: str | None = Depends(verify_api_key)):
    if not user_id:
        return []
    return await _get_controller().get_input_prompts(user_id)


@router.post("/api/input_prompt")
async def create_input_prompt(
    payload: InputPromptPayload,
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        return {"success": False, "detail": "Not authenticated"}
    return await _get_controller().create_input_prompt(
        user_id=user_id,
        payload=payload.model_dump(),
    )


@router.patch("/api/input_prompt/{prompt_id}")
async def update_input_prompt(
    prompt_id: int,
    payload: InputPromptPayload,
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        return {"success": False, "detail": "Not authenticated"}
    return await _get_controller().update_input_prompt(
        user_id=user_id,
        prompt_id=prompt_id,
        payload=payload.model_dump(),
    )


@router.delete("/api/input_prompt/{prompt_id}")
async def delete_input_prompt(
    prompt_id: int,
    user_id: str | None = Depends(verify_api_key),
):
    if not user_id:
        return {"success": False, "detail": "Not authenticated"}
    return await _get_controller().delete_input_prompt(user_id=user_id, prompt_id=prompt_id)


@router.get("/api/manage/connector-status")
async def get_connector_status():
    return await _get_controller().get_connector_status()


@router.get("/api/federated/oauth-status")
async def get_federated_oauth_status():
    return await _get_controller().get_federated_oauth_status()


@router.get("/api/manage/admin/valid-domains")
async def get_valid_domains():
    return await _get_controller().get_valid_domains()


@router.get("/api/manage/users/accepted")
async def get_accepted_users(
    page_num: int = 0,
    page_size: int = 20,
    q: str | None = None,
    is_active: bool | None = None,
    role: list[str] | None = Query(default=None),
):
    return await _get_controller().list_accepted_users_paginated(
        page_num=page_num,
        page_size=page_size,
        query=q,
        is_active=is_active,
        roles=role,
    )


@router.get("/api/manage/users/invited")
async def get_invited_users():
    return await _get_controller().get_invited_users()


@router.get("/api/manage/users")
async def get_all_users(include_api_keys: bool = False):
    return await _get_controller().get_all_users(include_api_keys)


@router.put("/api/manage/admin/users")
async def invite_users(payload: BulkInvitePayload):
    return await _get_controller().invite_users(payload.emails)


@router.post("/api/manage/admin/create-user")
async def create_user(payload: CreateUserPayload):
    return await _get_controller().create_user(
        email=payload.email,
        role=payload.role,
        first_name=payload.first_name,
        last_name=payload.last_name,
        password=payload.password,
    )


@router.patch("/api/manage/admin/update-user-profile")
async def update_user_profile(payload: UpdateUserProfilePayload):
    return await _get_controller().update_user_profile(
        user_email=payload.user_email,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )


@router.patch("/api/manage/admin/set-user-password")
async def set_user_password(payload: SetUserPasswordPayload):
    return await _get_controller().set_user_password(
        user_email=payload.user_email,
        password=payload.password,
        temporary=payload.temporary,
    )


@router.put("/api/manage/admin/remove-invited-user")
async def remove_invited_user(payload: UserEmailPayload):
    return await _get_controller().remove_invited_user(payload.user_email)


@router.patch("/api/manage/set-user-role")
async def set_user_role(payload: SetUserRolePayload):
    return await _get_controller().set_user_role(payload.user_email, payload.new_role)


@router.patch("/api/manage/admin/deactivate-user")
async def deactivate_user(payload: UserEmailPayload):
    return await _get_controller().set_user_active(payload.user_email, False)


@router.patch("/api/manage/admin/activate-user")
async def activate_user(payload: UserEmailPayload):
    return await _get_controller().set_user_active(payload.user_email, True)


@router.delete("/api/manage/admin/delete-user")
async def delete_user(payload: UserEmailPayload):
    return await _get_controller().delete_user(payload.user_email)


@router.put("/api/password/reset_password")
async def reset_user_password(payload: UserEmailPayload):
    return await _get_controller().reset_user_password(payload.user_email)


@router.get("/api/manage/users/download")
async def download_users():
    csv_data, filename = await _get_controller().download_users_csv()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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