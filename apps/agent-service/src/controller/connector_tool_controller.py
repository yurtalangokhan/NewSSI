"""Authorization and orchestration for saved connector tools."""

from typing import Any

from fastapi import HTTPException
from i18n import t

from repository.persona_repository import PersonaDB
from service.AuthService import AuthenticatedUser
from service.ConnectorToolService import get_connector_tool_service


class ConnectorToolController:
    def __init__(self, service: Any = None, personas: Any = None):
        self.service = service or get_connector_tool_service()
        if personas is None:
            from controller.persona_controller import get_persona_controller

            personas = get_persona_controller()
        self.personas = personas

    async def list_options(self) -> list[dict[str, Any]]:
        return await self.service.list_options()

    async def resolve(
        self, persona_id: int, datasource_id: str, operation: str, user_id: str
    ) -> dict[str, Any]:
        persona = await PersonaDB.get(persona_id)
        if not persona:
            raise HTTPException(
                403, detail=t("connectors.access_denied", default="Agent access denied.")
            )
        user = AuthenticatedUser(user_id=user_id, email="")
        restricted, accessible = await self.personas._load_agent_group_visibility(user)
        can_manage = await self.personas._can_manage_all_personas(user)
        if not self.personas._can_access_persona(persona, user, restricted, accessible, can_manage):
            raise HTTPException(
                403, detail=t("connectors.access_denied", default="Agent access denied.")
            )
        try:
            return await self.service.resolve(persona, datasource_id, operation)
        except PermissionError as exc:
            raise HTTPException(403, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc)) from None


def get_connector_tool_controller() -> ConnectorToolController:
    return ConnectorToolController()
