"""Controller for persona endpoints."""

from typing import Any

from fastapi import HTTPException

from controller.base import BaseController
from service.PersonaRepository import PersonaDB

USER_ID = "dev-user"


class PersonaController(BaseController):
    """Owns persona CRUD and persona-related helper endpoints."""

    async def get_personas(self) -> list[dict[str, Any]]:
        personas = []

        builtin_display = {
            "chatbot": "Chatbot",
            "configurable-mcp-agent": "Configurable MCP Agent",
        }
        for idx, (agent_key, display_name) in enumerate(builtin_display.items()):
            from agents.agents import agents as all_agents

            description = all_agents[agent_key].description if agent_key in all_agents else ""
            personas.append(
                {
                    "id": idx,
                    "name": display_name,
                    "description": description,
                    "tools": [],
                    "starter_messages": None,
                    "document_sets": [],
                    "is_public": True,
                    "is_visible": True,
                    "display_priority": None,
                    "featured": False,
                    "builtin_persona": True,
                    "labels": [],
                    "owner": {"id": "system", "email": "System"},
                    "base_agent": agent_key,
                    "mcp_tools": [],
                }
            )

        try:
            custom_personas = await PersonaDB.list_all(include_builtin=False)
            for persona in custom_personas:
                personas.append(
                    {
                        "id": persona["id"],
                        "name": persona["name"],
                        "description": persona["description"],
                        "tools": [],
                        "starter_messages": persona.get("starter_messages"),
                        "document_sets": [],
                        "is_public": persona.get("is_public", True),
                        "is_visible": True,
                        "display_priority": None,
                        "featured": False,
                        "builtin_persona": False,
                        "labels": persona.get("labels", []),
                        "owner": {"id": persona.get("user_id", USER_ID), "email": "dev@local.dev"},
                        "base_agent": persona.get("base_agent"),
                        "mcp_tools": persona.get("mcp_tools", []),
                    }
                )
        except Exception:
            pass

        return personas

    async def create_persona(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            persona = await PersonaDB.create(
                name=payload["name"],
                description=payload["description"],
                system_prompt=payload.get("system_prompt", ""),
                task_prompt=payload.get("task_prompt", ""),
                user_id=USER_ID,
                is_builtin=False,
                datetime_aware=payload.get("datetime_aware", True),
                is_public=payload.get("is_public", True),
                llm_model_provider_override=payload.get("llm_model_provider_override"),
                llm_model_version_override=payload.get("llm_model_version_override"),
                starter_messages=payload.get("starter_messages"),
                labels=payload.get("label_ids", []),
                base_agent=payload.get("base_agent"),
                mcp_tools=payload.get("mcp_tools") or [],
            )
        except Exception as exc:
            self._raise_internal_error(str(exc))

        return {
            "id": persona["id"],
            "name": persona["name"],
            "description": persona["description"],
            "tools": [],
            "starter_messages": persona.get("starter_messages"),
            "document_sets": [],
            "is_public": persona.get("is_public", True),
            "is_visible": True,
            "display_priority": None,
            "featured": False,
            "builtin_persona": False,
            "labels": persona.get("labels", []),
            "owner": {"id": USER_ID, "email": "dev@local.dev"},
            "base_agent": persona.get("base_agent"),
            "mcp_tools": persona.get("mcp_tools", []),
        }

    async def update_persona(self, persona_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            existing = await PersonaDB.get(persona_id)
            if existing and existing.get("is_builtin"):
                raise HTTPException(status_code=403, detail="Cannot update built-in agents")

            persona = await PersonaDB.update(
                persona_id,
                name=payload["name"],
                description=payload["description"],
                system_prompt=payload.get("system_prompt", ""),
                task_prompt=payload.get("task_prompt", ""),
                datetime_aware=payload.get("datetime_aware", True),
                is_public=payload.get("is_public", True),
                llm_model_provider_override=payload.get("llm_model_provider_override"),
                llm_model_version_override=payload.get("llm_model_version_override"),
                starter_messages=payload.get("starter_messages"),
                labels=payload.get("label_ids", []),
                base_agent=payload.get("base_agent"),
                mcp_tools=payload.get("mcp_tools") or [],
            )
            if not persona:
                self._raise_not_found("Persona not found")
        except HTTPException:
            raise
        except Exception as exc:
            self._raise_internal_error(str(exc))

        return {
            "id": persona["id"],
            "name": persona["name"],
            "description": persona["description"],
            "tools": [],
            "starter_messages": persona.get("starter_messages"),
            "document_sets": [],
            "is_public": persona.get("is_public", True),
            "is_visible": True,
            "display_priority": None,
            "featured": False,
            "builtin_persona": False,
            "labels": persona.get("labels", []),
            "owner": {"id": USER_ID, "email": "dev@local.dev"},
            "base_agent": persona.get("base_agent"),
            "mcp_tools": persona.get("mcp_tools", []),
        }

    async def delete_persona(self, persona_id: int) -> dict[str, bool]:
        try:
            persona = await PersonaDB.get(persona_id)
            if persona and persona.get("is_builtin"):
                raise HTTPException(status_code=403, detail="Cannot delete built-in agents")
            await PersonaDB.delete(persona_id)
        except HTTPException:
            raise
        except Exception as exc:
            self._raise_internal_error(str(exc))

        return {"success": True}

    async def upload_persona_image(self) -> dict[str, str]:
        return {"file_id": "mock-image-id"}

    async def get_persona_labels(self) -> list[Any]:
        return []


_persona_controller: PersonaController | None = None


def get_persona_controller() -> PersonaController:
    """Get singleton PersonaController."""
    global _persona_controller
    if _persona_controller is None:
        _persona_controller = PersonaController()
    return _persona_controller
