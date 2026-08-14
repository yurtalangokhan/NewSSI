"""
Persona/Assistant routes.

Endpoints: /api/persona/* (personas/assistants management)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from api.dependencies import AuthenticatedUser, require_permission, require_user
from controller import PersonaController, get_persona_controller
from models.personas import PersonaUpsertRequest

router = APIRouter(tags=["persona"], dependencies=[Depends(require_user)])


def _get_controller() -> PersonaController:
    return get_persona_controller()


@router.get("/api/persona")
async def get_personas(user: AuthenticatedUser = Depends(require_permission("persona:read"))):
    return await _get_controller().get_personas(user)


@router.get("/api/persona/options")
async def get_persona_options(
    user: AuthenticatedUser = Depends(require_permission("persona:read")),
):
    return await _get_controller().get_persona_options(user)


@router.get("/api/persona/labels")
async def get_persona_labels(
    _user: AuthenticatedUser = Depends(require_permission("persona:read")),
):
    return await _get_controller().get_persona_labels()


@router.post("/api/persona")
async def create_persona(
    persona_request: PersonaUpsertRequest,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("persona:create"))],
):
    return await _get_controller().create_persona(
        persona_request.model_dump(), request=request, user=user
    )


@router.get("/api/persona/{persona_id}")
async def get_persona(
    persona_id: int,
    user: AuthenticatedUser = Depends(require_permission("persona:read")),
):
    return await _get_controller().get_persona(persona_id, user)


@router.patch("/api/persona/{persona_id}")
async def update_persona(
    persona_id: int,
    request: PersonaUpsertRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("persona:update"))],
):
    return await _get_controller().update_persona(
        persona_id, request.model_dump(), user_id=user.user_id
    )


@router.delete("/api/persona/{persona_id}")
async def delete_persona(
    persona_id: int,
    _user: AuthenticatedUser = Depends(require_permission("persona:delete")),
):
    return await _get_controller().delete_persona(persona_id)


@router.post("/api/admin/persona/upload-image")
async def upload_persona_image(
    user: AuthenticatedUser = Depends(require_permission("persona:create")),
):
    return await _get_controller().upload_persona_image()
