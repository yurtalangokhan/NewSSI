"""
Persona/Assistant routes.

Endpoints: /api/persona/* (personas/assistants management)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from i18n import t

from api.dependencies import AuthenticatedUser, require_permission, require_user
from controller import PersonaController, get_persona_controller
from models.personas import PersonaUpsertRequest

router = APIRouter(tags=["persona"], dependencies=[Depends(require_user)])


def _get_controller() -> PersonaController:
    return get_persona_controller()


def _require_admin(user: AuthenticatedUser) -> AuthenticatedUser:
    admin_roles = {"admin", "super_admin", "superuser", "system-admin", "enterprise-admin"}
    if not admin_roles.intersection(role.lower() for role in user.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=t("auth.admin_required"))
    return user




@router.get("/api/persona")
async def get_personas(user: AuthenticatedUser = Depends(require_permission("persona:read"))):
    return await _get_controller().get_personas(user)


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
    admin = _require_admin(user)
    return await _get_controller().create_persona(
        persona_request.model_dump(), request=request, user=admin
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
    _require_admin(user)
    return await _get_controller().upload_persona_image()
