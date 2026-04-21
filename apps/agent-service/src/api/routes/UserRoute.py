"""
User preferences and settings routes.

Endpoints: /api/user/*, /api/llm/*, /admin/llm/*
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from controller import UserController, get_user_controller

router = APIRouter(tags=["user"])


def _get_controller() -> UserController:
    return get_user_controller()


class PinnedAssistantsUpdate(BaseModel):
    ordered_assistant_ids: list[int] = []


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
async def get_user_projects():
    return await _get_controller().get_user_projects()


@router.get("/api/notifications")
async def get_notifications():
    return await _get_controller().get_notifications()


@router.get("/api/input_prompt")
async def get_input_prompts():
    return await _get_controller().get_input_prompts()


@router.get("/api/manage/connector-status")
async def get_connector_status():
    return await _get_controller().get_connector_status()


@router.get("/api/federated/oauth-status")
async def get_federated_oauth_status():
    return await _get_controller().get_federated_oauth_status()


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