from typing import Annotated

from fastapi import APIRouter, Body, Depends

from src.api.dependencies import require_system_admin
from src.controller.system_settings_controller import get_system_settings_controller
from src.models.system_settings import KeycloakConfigUpdate, KeycloakRealmSessionUpdate

router = APIRouter(prefix="/system-settings", tags=["system-settings"])


@router.get("/keycloak")
async def get_keycloak_settings(
    _user_id: Annotated[str, Depends(require_system_admin)],
):
    return await get_system_settings_controller().get_keycloak_settings()


@router.patch("/keycloak")
async def update_keycloak_settings(
    payload: Annotated[KeycloakConfigUpdate, Body()],
    _user_id: Annotated[str, Depends(require_system_admin)],
):
    return await get_system_settings_controller().update_keycloak_settings(payload)


@router.patch("/keycloak/realm-session")
async def update_realm_session_settings(
    payload: Annotated[KeycloakRealmSessionUpdate, Body()],
    _user_id: Annotated[str, Depends(require_system_admin)],
):
    return await get_system_settings_controller().update_realm_session_settings(payload)


@router.post("/keycloak/external-idp/sync")
async def sync_external_identity_provider(
    _user_id: Annotated[str, Depends(require_system_admin)],
):
    return await get_system_settings_controller().sync_external_identity_provider()
