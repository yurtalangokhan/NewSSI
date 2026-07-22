"""Controller for persona endpoints."""

from typing import Any

from fastapi import HTTPException

from controller.base import BaseController
from core.settings import settings
from service.AuthService import AuthenticatedUser
from service.PersonaRepository import PersonaDB

DEFAULT_USER_ID = "dev-user"
ADMIN_ROLE_NAMES = {"admin", "system-admin", "enterprise-admin", "super_admin", "superuser"}


def build_agent_availability(
    agent: dict[str, Any],
    *,
    available_models: set[str],
    default_model: str | None,
    available_mcp_tools: set[str],
    available_rag_collections: set[str],
    available_graph_rag_collections: set[str],
    collection_display_names: dict[str, str] | None = None,
    memory_available: bool = True,
) -> dict[str, Any]:
    """Return component-level availability for an agent snapshot."""
    checks: list[dict[str, str]] = []
    selected_model = agent.get("llm_model_version_override") or agent.get("model")

    if selected_model:
        if selected_model in available_models:
            checks.append(
                {
                    "component": "model",
                    "status": "ok",
                    "message": f"Model '{selected_model}' is available.",
                }
            )
        else:
            checks.append(
                {
                    "component": "model",
                    "status": "error",
                    "message": f"Model '{selected_model}' is selected but is not available.",
                }
            )
    elif default_model:
        if default_model in available_models:
            checks.append(
                {
                    "component": "model",
                    "status": "ok",
                    "message": f"Using default model '{default_model}'.",
                }
            )
        else:
            checks.append(
                {
                    "component": "model",
                    "status": "error",
                    "message": f"Default model '{default_model}' is not available.",
                }
            )
    else:
        checks.append(
            {
                "component": "model",
                "status": "error",
                "message": "No default model is configured.",
            }
        )

    memory_enabled = agent.get("memory_type") == "long_term" or bool(agent.get("long_term_memory"))
    if memory_enabled:
        checks.append(
            {
                "component": "memory",
                "status": "ok" if memory_available else "error",
                "message": (
                    "Long-term memory is available."
                    if memory_available
                    else "Long-term memory is enabled but memory storage is not available."
                ),
            }
        )

    for tool_name in agent.get("mcp_tools") or []:
        checks.append(
            {
                "component": "mcp_tool",
                "status": "ok" if tool_name in available_mcp_tools else "error",
                "message": (
                    f"MCP tool '{tool_name}' is available."
                    if tool_name in available_mcp_tools
                    else f"MCP tool '{tool_name}' is selected but is not available."
                ),
            }
        )

    rag_config = agent.get("rag_config") or {}
    rag_config_display_names = rag_config.get("display_names") or {}
    if not isinstance(rag_config_display_names, dict):
        rag_config_display_names = {}
    collection_display_names = {
        **rag_config_display_names,
        **(collection_display_names or {}),
    }
    for collection in rag_config.get("document_processing") or []:
        display_name = collection_display_names.get(collection, collection)
        checks.append(
            {
                "component": "rag",
                "status": "ok" if collection in available_rag_collections else "error",
                "message": (
                    f"RAG collection '{display_name}' is available."
                    if collection in available_rag_collections
                    else f"RAG collection '{display_name}' is selected but is not available."
                ),
            }
        )

    for collection in rag_config.get("knowledge_graph") or []:
        display_name = collection_display_names.get(collection, collection)
        checks.append(
            {
                "component": "graph_rag",
                "status": "ok" if collection in available_graph_rag_collections else "error",
                "message": (
                    f"Graph RAG collection '{display_name}' is available."
                    if collection in available_graph_rag_collections
                    else f"Graph RAG collection '{display_name}' is selected but is not available."
                ),
            }
        )

    if any(check["status"] == "error" for check in checks):
        status_value = "unavailable"
    elif any(check["status"] == "warning" for check in checks):
        status_value = "degraded"
    else:
        status_value = "available"

    return {"status": status_value, "checks": checks}


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
                if user.user_id in {str(member_id) for member_id in group.get("user_ids", []) or []}
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
            "sub_agent_ids": payload.get("sub_agent_ids") or [],
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
                "llm_model_version_override": definition.model,
                "mcp_tools": definition.mcp_tools or [],
                "rag_config": definition.rag_config
                or {"document_processing": [], "knowledge_graph": []},
                "sub_agent_ids": definition.sub_agent_ids or [],
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

    async def _get_available_model_names(self) -> set[str]:
        try:
            from core.providers.registry import provider_registry

            provider_registry.initialize()
            return set(await provider_registry.get_model_names())
        except Exception:
            return set()

    async def _get_available_mcp_tool_names(self) -> set[str]:
        names: set[str] = set()
        try:
            from service.MCPToolService import MCPToolService

            tools = await MCPToolService.get_instance().list_tools(include_inactive=False)
            names.update(str(tool.get("name")) for tool in tools if tool.get("name"))
        except Exception:
            pass

        try:
            from controller.proxy_controller import get_proxy_controller

            tools_service_url = (
                getattr(settings, "TOOLS_SERVICE_URL", None) or settings.MCP_SERVER_URL
            )
            payload = await get_proxy_controller().get_builtin_mcp_tools(tools_service_url)
            names.update(str(tool.get("name")) for tool in payload.get("tools", []))
        except Exception:
            pass

        return names

    async def _get_existing_collection_info(
        self,
        collection_ids: list[str],
    ) -> tuple[set[str], dict[str, str]]:
        if not collection_ids:
            return set(), {}

        existing: set[str] = set()
        display_names: dict[str, str] = {}
        try:
            from core.db.repositories.datasource_repo import DatasourceRepository

            repo = DatasourceRepository()
            for collection_id in collection_ids:
                collection = await repo.get_collection(collection_id)
                if collection is None:
                    collection = await repo.get_collection_by_name(collection_id)
                if collection is not None:
                    existing.add(collection_id)
                    display_name = collection.get("name") or collection.get("uuid")
                    if display_name:
                        display_names[collection_id] = str(display_name)
        except Exception:
            return set(), {}

        return existing, display_names

    def _is_memory_available(self) -> bool:
        try:
            from service.LangGraphStoreService import get_langgraph_store

            return get_langgraph_store() is not None
        except Exception:
            return False

    async def _get_agent_availability(self, agent: dict[str, Any]) -> dict[str, Any]:
        rag_config = agent.get("rag_config") or {}
        document_collections = [str(c) for c in rag_config.get("document_processing") or []]
        graph_collections = [str(c) for c in rag_config.get("knowledge_graph") or []]

        available_models = await self._get_available_model_names()
        available_mcp_tools = await self._get_available_mcp_tool_names()
        available_rag_collections, rag_display_names = await self._get_existing_collection_info(
            document_collections
        )
        (
            available_graph_rag_collections,
            graph_display_names,
        ) = await self._get_existing_collection_info(graph_collections)
        collection_display_names = {**rag_display_names, **graph_display_names}

        return build_agent_availability(
            agent,
            available_models=available_models,
            default_model=settings.DEFAULT_MODEL,
            available_mcp_tools=available_mcp_tools,
            available_rag_collections=available_rag_collections,
            available_graph_rag_collections=available_graph_rag_collections,
            collection_display_names=collection_display_names,
            memory_available=self._is_memory_available(),
        )

    async def _serialize_builtin_persona(
        self, persona_id: int, name: str, description: str, base_agent: str
    ) -> dict[str, Any]:
        serialized = {
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
        serialized["availability"] = await self._get_agent_availability(serialized)
        return serialized

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
            "replace_base_system_prompt": bool(persona.get("replace_base_system_prompt", False)),
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
        serialized["availability"] = await self._get_agent_availability(serialized)
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

            description = all_agents[base_agent].description if base_agent in all_agents else ""
            return await self._serialize_builtin_persona(
                persona_id, display_name, description, base_agent
            )

        persona = await PersonaDB.get(persona_id)
        if not persona:
            self._raise_not_found("Persona not found")

        if user:
            (
                restricted_persona_ids,
                accessible_persona_ids,
            ) = await self._load_agent_group_visibility(user)
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
                await self._serialize_builtin_persona(idx, display_name, description, agent_key)
            )

        try:
            custom_personas = await PersonaDB.list_all(include_builtin=False)
            restricted_persona_ids: set[int] = set()
            accessible_persona_ids: set[int] = set()
            if user:
                (
                    restricted_persona_ids,
                    accessible_persona_ids,
                ) = await self._load_agent_group_visibility(user)
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
