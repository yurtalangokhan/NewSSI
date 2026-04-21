"""
Persona/Assistant routes.

Endpoints: /api/persona/* (personas/assistants management)
"""

from fastapi import APIRouter
from pydantic import BaseModel

from controller import PersonaController, get_persona_controller

router = APIRouter(tags=["persona"])


def _get_controller() -> PersonaController:
    return get_persona_controller()


@router.get("/api/persona")
async def get_personas():
    return await _get_controller().get_personas()


class PersonaUpsertRequest(BaseModel):
    name: str
    description: str
    system_prompt: str = ""
    task_prompt: str = ""
    datetime_aware: bool = True
    document_set_ids: list = []
    is_public: bool = True
    llm_model_provider_override: str | None = None
    llm_model_version_override: str | None = None
    starter_messages: list | None = None
    users: list = []
    groups: list = []
    tool_ids: list = []
    remove_image: bool = False
    uploaded_image_id: str | None = None
    icon_name: str | None = None
    search_start_date: str | None = None
    featured: bool = False
    display_priority: int | None = None
    label_ids: list = []
    user_file_ids: list = []
    replace_base_system_prompt: bool = False
    hierarchy_node_ids: list = []
    document_ids: list = []
    base_agent: str | None = None
    mcp_tools: list[str] = []


@router.post("/api/persona")
async def create_persona(request: PersonaUpsertRequest):
    return await _get_controller().create_persona(request.model_dump())


@router.patch("/api/persona/{persona_id}")
async def update_persona(persona_id: int, request: PersonaUpsertRequest):
    return await _get_controller().update_persona(persona_id, request.model_dump())


@router.delete("/api/persona/{persona_id}")
async def delete_persona(persona_id: int):
    return await _get_controller().delete_persona(persona_id)


@router.post("/api/admin/persona/upload-image")
async def upload_persona_image():
    return await _get_controller().upload_persona_image()


@router.get("/api/persona/labels")
async def get_persona_labels():
    return await _get_controller().get_persona_labels()