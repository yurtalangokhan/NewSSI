"""Controller for persona endpoints."""

from typing import Any

from fastapi import HTTPException

from controller.base import BaseController
from service.AuthService import AuthenticatedUser
from service.PersonaRepository import PersonaDB

DEFAULT_USER_ID = "dev-user"
ADMIN_ROLE_NAMES = {"admin", "system-admin", "enterprise-admin", "super_admin", "superuser"}


def _format_tool_display_name(tool_name: str) -> str:
    return tool_name.replace("_", " ").replace("-", " ").title()


class PersonaController(BaseController):
    """Owns persona CRUD and persona-related helper endpoints."""

    @staticmethod
    def _dynamic_definition_name(persona_id: int) -> str:
        return f"persona-{persona_id}"

    async def _get_dynamic_definition(self, persona_id: int):
        from agents.storage.repository import AgentDefinitionRepository

        return await AgentDefinitionRepository().get_by_persona_id(persona_id)

    @staticmethod
    def _is_admin_user(user: AuthenticatedUser) -> bool:
        return bool({role.lower() for role in user.roles} & ADMIN_ROLE_NAMES)

    @staticmethod
    def _group_persona_ids(groups: list[dict[str, Any]]) -> set[int]:
        persona_ids: set[int] = set()
        for group in groups:
            for persona_id in group.get("persona_ids", []) or []:
                try:
                    persona_ids.add(int(persona_id))
                except (TypeError, ValueError):
                    continue
        return persona_ids

    async def _load_agent_group_visibility(
        self,
        user: AuthenticatedUser,
    ) -> tuple[set[int], set[int]]:
        from core.db.repositories.agent_group_repo import AgentGroupRepository

        groups = await AgentGroupRepository().list_all()
        restricted_persona_ids = self._group_persona_ids(groups)
        accessible_persona_ids = self._group_persona_ids(
            [
                group
                for group in groups
                if user.user_id
                in {str(member_id) for member_id in group.get("user_ids", []) or []}
            ]
        )
        return restricted_persona_ids, accessible_persona_ids

    def _can_access_persona(
        self,
        persona: dict[str, Any],
        user: AuthenticatedUser,
        restricted_persona_ids: set[int],
        accessible_persona_ids: set[int],
    ) -> bool:
        if self._is_admin_user(user):
            return True

        persona_id = int(persona["id"])
        if str(persona.get("user_id") or "") == user.user_id:
            return True

        if persona_id in restricted_persona_ids:
            return persona_id in accessible_persona_ids

        return bool(persona.get("is_public", True))

    def _dynamic_payload_from_persona_payload(
        self,
        payload: dict[str, Any],
        persona: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "graph_schema": payload.get("graph_schema") or "zero_shot",
            "brain_type": payload.get("brain_type") or "llm",
            "memory_type": payload.get("memory_type") or "none",
            "system_prompt": payload.get("system_prompt") or None,
            "model": payload.get("llm_model_version_override") or None,
            "mcp_tools": payload.get("mcp_tools") or [],
            "rag_config": payload.get("rag_config")
            or {"document_processing": [], "knowledge_graph": []},
            "sub_agents": payload.get("sub_agents") or [],
            "supervisor_prompt": payload.get("supervisor_prompt"),
            "stages": payload.get("stages") or [],
            "pipeline_prompt": payload.get("pipeline_prompt"),
            "reflection_prompt": payload.get("reflection_prompt"),
            "max_iterations": payload.get("max_iterations") or 3,
            "description": payload.get("description") or None,
            "tags": [],
            "is_active": True,
            "name": self._dynamic_definition_name(int(persona["id"])),
        }

    async def _upsert_dynamic_definition(
        self,
        payload: dict[str, Any],
        persona: dict[str, Any],
    ) -> None:
        if payload.get("base_agent") != "dynamic-agent":
            return

        from agents.storage.repository import AgentDefinitionRepository
        from domain.agents.service import AgentDefinitionService

        repo = AgentDefinitionRepository()
        service = AgentDefinitionService(repo)
        persona_id = int(persona["id"])
        definition = await repo.get_by_persona_id(persona_id)
        dynamic_payload = self._dynamic_payload_from_persona_payload(payload, persona)

        if definition:
            await service.update_agent_definition(definition.id, dynamic_payload)
            return

        create_payload = {
            key: value for key, value in dynamic_payload.items() if key != "is_active"
        }
        await service.create_agent_definition(
            persona_id=persona_id,
            **create_payload,
        )

    def _merge_dynamic_definition(
        self,
        serialized: dict[str, Any],
        definition: Any | None,
    ) -> dict[str, Any]:
        if not definition:
            return serialized

        serialized.update(
            {
                "is_dynamic": True,
                "graph_schema": definition.graph_schema,
                "brain_type": definition.brain_type,
                "memory_type": definition.memory_type,
                "mcp_tools": definition.mcp_tools or [],
                "rag_config": definition.rag_config
                or {"document_processing": [], "knowledge_graph": []},
                "sub_agents": definition.sub_agents or [],
                "supervisor_prompt": definition.supervisor_prompt,
                "stages": definition.stages or [],
                "pipeline_prompt": definition.pipeline_prompt,
                "reflection_prompt": definition.reflection_prompt,
                "max_iterations": definition.max_iterations,
            }
        )
        return serialized

    def _resolve_owner_email(self, persona: dict[str, Any]) -> str:
        stored_email = persona.get("user_email")
        if isinstance(stored_email, str) and stored_email.strip():
            return stored_email

        owner_id = str(persona.get("user_id") or DEFAULT_USER_ID)
        if "@" in owner_id:
            return owner_id

        return "user@local.dev"

    def _extract_rag_tool_names(self, rag_config: dict[str, Any] | None) -> list[str]:
        rag = rag_config or {}
        tool_names: list[str] = []

        if rag.get("document_processing"):
            tool_names.append("database_search")
        if rag.get("knowledge_graph"):
            tool_names.append("graph_search")

        return tool_names

    def _build_tool_snapshots(
        self,
        persona_id: int,
        mcp_tool_names: list[str] | None,
        rag_config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        tool_snapshots: list[dict[str, Any]] = []
        mcp_tool_names = mcp_tool_names or []
        rag_tool_names = self._extract_rag_tool_names(rag_config)
        seen_names: set[str] = set()

        def add_tool_snapshot(tool_name: str, is_mcp_tool: bool) -> None:
            if tool_name in seen_names:
                return
            seen_names.add(tool_name)

            index = len(tool_snapshots)
            tool_snapshots.append(
                {
                    "id": (persona_id * 1000) + index + 1,
                    "name": tool_name,
                    "display_name": _format_tool_display_name(tool_name),
                    "description": "",
                    "definition": None,
                    "custom_headers": [],
                    "in_code_tool_id": tool_name,
                    "passthrough_auth": False,
                    "oauth_config_id": None,
                    "oauth_config_name": None,
                    "mcp_server_id": 1 if is_mcp_tool else None,
                    "user_id": None,
                    "enabled": True,
                    "chat_selectable": True,
                    "agent_creation_selectable": True,
                    "default_enabled": False,
                }
            )

        for tool_name in mcp_tool_names:
            add_tool_snapshot(tool_name, is_mcp_tool=True)

        for tool_name in rag_tool_names:
            add_tool_snapshot(tool_name, is_mcp_tool=False)

        return tool_snapshots

    def _serialize_builtin_persona(
        self, persona_id: int, name: str, description: str, base_agent: str
    ) -> dict[str, Any]:
        return {
            "id": persona_id,
            "name": name,
            "description": description,
            "tools": [],
            "starter_messages": None,
            "document_sets": [],
            "hierarchy_node_count": 0,
            "attached_document_count": 0,
            "knowledge_sources": [],
            "llm_model_version_override": None,
            "llm_model_provider_override": None,
            "uploaded_image_id": None,
            "icon_name": None,
            "is_public": True,
            "is_visible": True,
            "display_priority": None,
            "featured": False,
            "builtin_persona": True,
            "labels": [],
            "owner": {"id": "system", "email": "System"},
            "user_file_ids": [],
            "users": [],
            "groups": [],
            "hierarchy_nodes": [],
            "attached_documents": [],
            "system_prompt": "",
            "replace_base_system_prompt": False,
            "task_prompt": "",
            "datetime_aware": True,
            "base_agent": base_agent,
            "mcp_tools": [],
            "rag_config": {
                "document_processing": [],
                "knowledge_graph": [],
            },
            "search_start_date": None,
        }

    async def _serialize_custom_persona(self, persona: dict[str, Any]) -> dict[str, Any]:
        label_ids = persona.get("labels") or []
        labels = [
            label if isinstance(label, dict) else {"id": label, "name": f"Label {label}"}
            for label in label_ids
        ]
        mcp_tools = persona.get("mcp_tools") or []
        rag_config = persona.get("rag_config") or {
            "document_processing": [],
            "knowledge_graph": [],
        }

        serialized = {
            "id": persona["id"],
            "name": persona["name"],
            "description": persona["description"],
            "tools": self._build_tool_snapshots(persona["id"], mcp_tools, rag_config),
            "starter_messages": persona.get("starter_messages"),
            "document_sets": [],
            "hierarchy_node_count": 0,
            "attached_document_count": 0,
            "knowledge_sources": [],
            "llm_model_version_override": persona.get("llm_model_version_override"),
            "llm_model_provider_override": persona.get("llm_model_provider_override"),
            "uploaded_image_id": persona.get("uploaded_image_id"),
            "icon_name": persona.get("icon_name"),
            "is_public": persona.get("is_public", True),
            "is_visible": True,
            "display_priority": persona.get("display_priority"),
            "featured": bool(persona.get("featured", False)),
            "builtin_persona": False,
            "labels": labels,
            "owner": {
                "id": str(persona.get("user_id") or DEFAULT_USER_ID),
                "email": self._resolve_owner_email(persona),
            },
            "user_file_ids": persona.get("user_file_ids") or [],
            "users": persona.get("users") or [],
            "groups": persona.get("groups") or [],
            "hierarchy_nodes": persona.get("hierarchy_nodes") or [],
            "attached_documents": persona.get("attached_documents") or [],
            "system_prompt": persona.get("system_prompt", ""),
            "replace_base_system_prompt": bool(
                persona.get("replace_base_system_prompt", False)
            ),
            "task_prompt": persona.get("task_prompt", ""),
            "datetime_aware": bool(persona.get("datetime_aware", True)),
            "base_agent": persona.get("base_agent"),
            "mcp_tools": mcp_tools,
            "rag_config": rag_config,
            "long_term_memory": bool(persona.get("long_term_memory", False)),
            "search_start_date": persona.get("search_start_date"),
        }
        if persona.get("base_agent") == "dynamic-agent":
            definition = await self._get_dynamic_definition(int(persona["id"]))
            self._merge_dynamic_definition(serialized, definition)
        return serialized

    async def get_persona(
        self,
        persona_id: int,
        user: AuthenticatedUser | None = None,
    ) -> dict[str, Any]:
        builtin_display = {
            0: ("Chatbot", "chatbot"),
            1: ("Configurable MCP Agent", "configurable-mcp-agent"),
        }

        if persona_id in builtin_display:
            display_name, base_agent = builtin_display[persona_id]
            from agents.agents import agents as all_agents

            description = (
                all_agents[base_agent].description if base_agent in all_agents else ""
            )
            return self._serialize_builtin_persona(
                persona_id, display_name, description, base_agent
            )

        persona = await PersonaDB.get(persona_id)
        if not persona:
            self._raise_not_found("Persona not found")

        if user:
            restricted_persona_ids, accessible_persona_ids = (
                await self._load_agent_group_visibility(user)
            )
            if not self._can_access_persona(
                persona,
                user,
                restricted_persona_ids,
                accessible_persona_ids,
            ):
                self._raise_not_found("Persona not found")

        return await self._serialize_custom_persona(persona)

    async def get_personas(
        self,
        user: AuthenticatedUser | None = None,
    ) -> list[dict[str, Any]]:
        personas = []

        builtin_display = {
            "chatbot": "Chatbot",
            "configurable-mcp-agent": "Configurable MCP Agent",
        }
        for idx, (agent_key, display_name) in enumerate(builtin_display.items()):
            from agents.agents import agents as all_agents

            description = all_agents[agent_key].description if agent_key in all_agents else ""
            personas.append(
                self._serialize_builtin_persona(idx, display_name, description, agent_key)
            )

        try:
            custom_personas = await PersonaDB.list_all(include_builtin=False)
            restricted_persona_ids: set[int] = set()
            accessible_persona_ids: set[int] = set()
            if user:
                restricted_persona_ids, accessible_persona_ids = (
                    await self._load_agent_group_visibility(user)
                )
            for persona in custom_personas:
                if user and not self._can_access_persona(
                    persona,
                    user,
                    restricted_persona_ids,
                    accessible_persona_ids,
                ):
                    continue
                personas.append(await self._serialize_custom_persona(persona))
        except Exception:
            pass

        return personas

    async def create_persona(
        self,
        payload: dict[str, Any],
        user_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            rag_config = payload.get("rag_config")
            effective_user_id = user_id or DEFAULT_USER_ID
            persona = await PersonaDB.create(
                name=payload["name"],
                description=payload["description"],
                system_prompt=payload.get("system_prompt", ""),
                task_prompt=payload.get("task_prompt", ""),
                user_id=effective_user_id,
                is_builtin=False,
                datetime_aware=payload.get("datetime_aware", True),
                is_public=payload.get("is_public", True),
                llm_model_provider_override=payload.get("llm_model_provider_override"),
                llm_model_version_override=payload.get("llm_model_version_override"),
                starter_messages=payload.get("starter_messages"),
                labels=payload.get("label_ids", []),
                base_agent=payload.get("base_agent"),
                mcp_tools=payload.get("mcp_tools") or [],
                rag_config=rag_config,
                long_term_memory=bool(payload.get("long_term_memory", False)),
            )
        except Exception as exc:
            self._raise_internal_error(str(exc))

        try:
            await self._upsert_dynamic_definition(payload, persona)
        except Exception as exc:
            await PersonaDB.delete(int(persona["id"]))
            self._raise_internal_error(str(exc))
        return await self._serialize_custom_persona(persona)

    async def update_persona(
        self,
        persona_id: int,
        payload: dict[str, Any],
        user_id: str | None = None,
    ) -> dict[str, Any]:
        _ = user_id
        try:
            existing = await PersonaDB.get(persona_id)
            if existing and existing.get("is_builtin"):
                raise HTTPException(status_code=403, detail="Cannot update built-in agents")

            rag_config = payload.get("rag_config")
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
                rag_config=rag_config,
                long_term_memory=bool(payload.get("long_term_memory", False)),
            )
            if not persona:
                self._raise_not_found("Persona not found")
        except HTTPException:
            raise
        except Exception as exc:
            self._raise_internal_error(str(exc))

        await self._upsert_dynamic_definition(payload, persona)
        return await self._serialize_custom_persona(persona)

    async def delete_persona(self, persona_id: int) -> dict[str, bool]:
        try:
            persona = await PersonaDB.get(persona_id)
            if persona and persona.get("is_builtin"):
                raise HTTPException(status_code=403, detail="Cannot delete built-in agents")
            if persona and persona.get("base_agent") == "dynamic-agent":
                definition = await self._get_dynamic_definition(persona_id)
                if definition:
                    from agents.storage.repository import AgentDefinitionRepository

                    await AgentDefinitionRepository().delete(definition.id)
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
