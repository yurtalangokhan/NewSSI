"""Persona service for managing personas and configurations."""

import asyncio
from dataclasses import replace
import json
from typing import Any
import uuid

from config_manager import env
from error_contract import AgentNotFoundError, DependencyResponseError, PayloadTooLargeError
import httpx
from localization import get_locale

from agents.knowledge.tool_selector import KnowledgeToolSelector
from core.exceptions import ApplicationError, BadRequestError, ForbiddenError
from core.http import outbound
from core.observability.logger import get_logger
from infrastructure.db.persistence_gateway import (
    agent_definition_repository,
    document_repository,
    flow_version_repository,
    persona_repository,
    provider_repository,
)
from service.auth.auth_service import AuthenticatedUser, get_auth_service, get_primary_user_id
from service.common.base import BaseService
from service.common.uploads import UploadedFile
from service.personas.persona_access import (
    PersonaAccessPolicy,
    group_persona_ids,
    permission_user_id,
)
from service.personas.persona_helpers import (
    RAG_TOOL_NAMES,
    _format_tool_display_name,
    _has_web_search_tool,
    _is_uuid_owner_id,
    _parse_mcp_tool_description,
    _rag_tool_metadata,
    build_agent_availability,
    flow_meta_fields,
)

DEFAULT_USER_ID = "dev-user"
CATALOG_AVAILABILITY_TIMEOUT_SECONDS = 5.0
logger = get_logger(__name__)


class PersonaService(BaseService):
    """Owns persona CRUD and persona-related helper endpoints."""

    #: Visibility rules, shared with ConnectorToolService. A class attribute
    #: rather than constructor state: the policy is stateless, and every test
    #: that stubs the private wrappers below keeps working untouched.
    _access: PersonaAccessPolicy = PersonaAccessPolicy()

    async def _validate_connector_bindings(self, payload: dict[str, Any], user_id: str) -> list[dict[str, Any]]:
        bindings = payload.get("connector_bindings") or []
        if not bindings:
            return []
        from service.orchestration.connector_tool_service import get_connector_tool_service

        return await get_connector_tool_service().validate_bindings(
            bindings, base_agent=payload.get("base_agent"), user_id=user_id
        )

    @property
    def _mail_config_service(self):
        service = getattr(self, "__mail_config_service", None)
        if service is None:
            from service.auth.mail_config_service import get_mail_config_service

            service = get_mail_config_service()
            setattr(self, "__mail_config_service", service)
        return service

    @_mail_config_service.setter
    def _mail_config_service(self, value):
        setattr(self, "__mail_config_service", value)

    @staticmethod
    def _dynamic_definition_name(persona_id: int) -> str:
        return f"persona-{persona_id}"

    async def _validate_mcp_tool_configs(
        self,
        *,
        user_id: str,
        mcp_tools: list[str],
        mcp_tool_configs: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if "send_email" not in (mcp_tools or []):
            return {}

        configs = mcp_tool_configs or {}
        send_email_config = configs.get("send_email")
        if not isinstance(send_email_config, dict):
            raise BadRequestError(code="mail.config_required", message_key="errors.mail.config_required")

        mail_config_id = str(send_email_config.get("mail_config_id") or "").strip()
        if not mail_config_id:
            raise BadRequestError(code="mail.config_required", message_key="errors.mail.config_required")

        mail_config = await self._mail_config_service.get_config(user_id, mail_config_id)
        if not mail_config:
            raise BadRequestError(message_key="errors.mail.config_not_found")

        return {"send_email": {"mail_config_id": mail_config_id}}

    async def resolve_owner_user_id(
        self,
        auth_token: str | None,
        user: AuthenticatedUser,
    ) -> str:
        """Resolve the id that owns a persona from an already-extracted token.

        The token arrives from the API layer rather than a ``Request``: pulling
        it out of the transport is the route's job, which keeps this service
        free of any FastAPI dependency.
        """
        identity = await get_auth_service().resolve_user_identity(token=auth_token, user_id=user.user_id, user=user)
        return get_primary_user_id(identity, user.user_id) or user.user_id

    async def _get_dynamic_definition(self, persona_id: int):
        return await agent_definition_repository().get_by_persona_id(persona_id)

    @staticmethod
    def _permission_user_id(user: AuthenticatedUser) -> str:
        return permission_user_id(user)

    async def _resolve_access_user(self, user: AuthenticatedUser) -> AuthenticatedUser:
        """Resolve owner identity without mutating the authenticated token claims."""
        identity = await get_auth_service().resolve_user_identity(
            token=user.access_token, user_id=user.user_id, user=user
        )
        local_user = identity.get("user_service_user")
        if isinstance(local_user, dict) and local_user.get("id"):
            return replace(user, claims={**user.claims, "user_service_user": local_user})
        return user

    async def _can_manage_all_personas(self, user: AuthenticatedUser) -> bool:
        return await self._access.can_manage_all(user)

    @staticmethod
    def _group_persona_ids(groups: list[dict[str, Any]]) -> set[int]:
        return group_persona_ids(groups)

    async def _load_agent_group_visibility(
        self,
        user: AuthenticatedUser,
    ) -> tuple[set[int], set[int]]:
        return await self._access.load_visibility(user)

    def _can_access_persona(
        self,
        persona: dict[str, Any],
        user: AuthenticatedUser,
        restricted_persona_ids: set[int],
        accessible_persona_ids: set[int],
        can_manage_all_personas: bool,
    ) -> bool:
        return self._access.can_access(
            persona,
            user,
            restricted_persona_ids,
            accessible_persona_ids,
            can_manage_all_personas,
        )

    def _dynamic_payload_from_persona_payload(
        self,
        payload: dict[str, Any],
        persona: dict[str, Any],
        definition: Any | None = None,
    ) -> dict[str, Any]:
        # A PATCH that doesn't resend `graph_schema` (e.g. a plain rename)
        # must not silently reset an existing flow-backed definition to
        # "zero_shot" — that severs it from its `flow_spec` (agent_factory.py
        # only builds a `FlowAgent` when `graph_schema == "flow"`) on the
        # very next chat request, with no error anywhere in between. Falls
        # back to the definition's own current value first, "zero_shot"
        # only when there's no definition yet (a brand-new dynamic agent).
        existing_graph_schema = definition.graph_schema if definition else None
        return {
            "graph_schema": payload.get("graph_schema") or existing_graph_schema or "zero_shot",
            "brain_type": payload.get("brain_type") or "llm",
            "memory_type": payload.get("memory_type") or "none",
            "system_prompt": payload.get("system_prompt") or None,
            "model": payload.get("llm_model_version_override") or None,
            "mcp_tools": payload.get("mcp_tools") or [],
            "mcp_tool_configs": payload.get("mcp_tool_configs") or {},
            "rag_config": payload.get("rag_config") or {"document_processing": [], "knowledge_graph": []},
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

        from service.agent_definitions.agent_definition_service import AgentDefinitionService

        repo = agent_definition_repository()
        service = AgentDefinitionService(repo)
        persona_id = int(persona["id"])
        definition = await repo.get_by_persona_id(persona_id)
        dynamic_payload = self._dynamic_payload_from_persona_payload(payload, persona, definition)

        if definition:
            await service.update_agent_definition(definition.id, dynamic_payload)
            return

        create_payload = {key: value for key, value in dynamic_payload.items() if key != "is_active"}
        await service.create_agent_definition(
            persona_id=persona_id,
            **create_payload,
        )

    def _merge_dynamic_definition(
        self,
        serialized: dict[str, Any],
        definition: Any | None,
        flow_summaries: dict[Any, Any] | None = None,
    ) -> dict[str, Any]:
        if not definition:
            return serialized

        serialized.update(
            {
                "is_dynamic": True,
                # (UUID) to call the flow draft/versions/publish endpoints
                # (flow_versions_route.py) — those take `definition_id`, not
                # this persona's own numeric `id`. Never exposed before
                # this task; a flow-backed persona's canvas had no way to
                # know which definition row to talk to.
                "agent_definition_id": str(definition.id),
                "graph_schema": definition.graph_schema,
                "brain_type": definition.brain_type,
                "memory_type": definition.memory_type,
                "llm_model_version_override": definition.model,
                "mcp_tools": definition.mcp_tools or [],
                "mcp_tool_configs": getattr(definition, "mcp_tool_configs", {}) or {},
                "rag_config": definition.rag_config or {"document_processing": [], "knowledge_graph": []},
                "sub_agent_ids": definition.sub_agent_ids or [],
                "sub_agents": definition.sub_agents or [],
                "supervisor_prompt": definition.supervisor_prompt,
                "stages": definition.stages or [],
                "pipeline_prompt": definition.pipeline_prompt,
                "reflection_prompt": definition.reflection_prompt,
                "max_iterations": definition.max_iterations,
            }
        )
        serialized.update(flow_meta_fields(definition, flow_summaries))
        return serialized

    def _resolve_owner_email(
        self,
        persona: dict[str, Any],
        owner_emails: dict[str, str] | None = None,
    ) -> str:
        owner_id = str(persona.get("user_id") or DEFAULT_USER_ID)
        if "@" in owner_id:
            return owner_id
        if persona.get("user_email"):
            return str(persona["user_email"])

        stored_email = persona.get("user_email")
        if isinstance(stored_email, str) and stored_email.strip() and not _is_uuid_owner_id(owner_id):
            return stored_email

        return (owner_emails or {}).get(owner_id, "Unknown user")

    async def _load_owner_emails(
        self,
        personas: list[dict[str, Any]],
        current_user: AuthenticatedUser | None = None,
    ) -> dict[str, str]:
        owner_ids = list(
            dict.fromkeys(
                owner_id
                for persona in personas
                if (owner_id := str(persona.get("user_id") or ""))
                and "@" not in owner_id
                and _is_uuid_owner_id(owner_id)
            )
        )[:100]
        result: dict[str, str] = {}
        if current_user and getattr(current_user, "email", None) and getattr(current_user, "user_id", None):
            result[str(current_user.user_id)] = str(current_user.email)

        if not owner_ids:
            return result

        try:
            from integrations.user_service_client import get_users_by_ids

            users = await get_users_by_ids(owner_ids)
            result.update(
                {str(user["id"]): str(user["email"]) for user in users if user.get("id") and user.get("email")}
            )
        except Exception:
            logger.warning("Failed to resolve persona owner emails", exc_info=True)

        return result

    def _build_tool_snapshots(
        self,
        persona_id: int,
        mcp_tool_names: list[str] | None,
        rag_config: dict[str, Any] | None = None,
        *,
        tool_descriptions: dict[str, dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        tool_snapshots: list[dict[str, Any]] = []
        mcp_tool_names = mcp_tool_names or []
        rag = rag_config or {}
        collection_display_names = rag.get("display_names") or {}
        seen_keys: set[str] = set()
        tool_descriptions = tool_descriptions or {}

        def add_tool_snapshot(
            tool_name: str,
            is_mcp_tool: bool,
            *,
            dedupe_key: str | None = None,
            display_name_override: str | None = None,
        ) -> None:
            key = dedupe_key or tool_name
            if key in seen_keys:
                return
            seen_keys.add(key)

            if tool_name in RAG_TOOL_NAMES:
                meta = _rag_tool_metadata(tool_name)
            else:
                meta = tool_descriptions.get(tool_name) or {}

            description = meta.get("description", "")
            display_name = display_name_override or meta.get("display_name") or _format_tool_display_name(tool_name)

            index = len(tool_snapshots)
            tool_snapshots.append(
                {
                    "id": (persona_id * 1000) + index + 1,
                    "name": tool_name,
                    "display_name": display_name,
                    "description": description,
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

        # One row per assigned collection, labeled with that collection's own
        # name, instead of one generic placeholder per RAG kind — the chat
        # input bar's tools popover renders this list as-is.
        for tool_name, collection_ids in KnowledgeToolSelector.select_collections(rag).items():
            for collection_id in collection_ids:
                add_tool_snapshot(
                    tool_name,
                    is_mcp_tool=False,
                    dedupe_key=f"{tool_name}:{collection_id}",
                    display_name_override=collection_display_names.get(collection_id),
                )

        return tool_snapshots

    async def _get_available_model_names(self, user_id: str | None = None) -> set[str]:
        model_names: set[str] = set()
        try:
            from infrastructure.llm.adapters.registry import provider_registry

            provider_registry.initialize()
            model_names.update(await provider_registry.get_model_names())
        except Exception:
            logger.warning("Could not load provider model names; catalog availability may be incomplete", exc_info=True)

        try:
            from service.model_providers.model_provider_service import ProviderService

            repo = provider_repository()
            svc = ProviderService(repo)
            providers = await svc.get_available_models_for_user(user_id or DEFAULT_USER_ID)
            for p in providers:
                for mc in p.get("model_configurations", []):
                    name = mc.get("name")
                    if name:
                        model_names.add(name)
        except Exception:
            logger.warning(
                "Could not load provider models for user; catalog availability may be incomplete", exc_info=True
            )

        return model_names

    async def _get_mcp_tool_metadata(self) -> dict[str, dict[str, str]]:
        """Name -> {"description", "display_name"} for every registered/
        built-in MCP tool, translated to the current request's locale.

        Both sources can embed tools-service's `[category:...]
        [category_label:...][title:...]` tags in the raw description (see
        `_parse_mcp_tool_description`); those are stripped here so callers
        never see them, and the title tag (when present) supplies a
        localized display name instead of the generic snake_case-to-title
        fallback.

        Callers that need to check *whether* a tool exists but not its
        metadata can use `_get_available_mcp_tool_names`, which derives its
        result from this so the two never disagree.
        """
        descriptions: dict[str, dict[str, str]] = {}

        def _record(name: object, raw_description: object) -> None:
            if not name:
                return
            clean_description, title = _parse_mcp_tool_description(str(raw_description or ""))
            descriptions[str(name)] = {
                "description": clean_description,
                "display_name": title or "",
            }

        try:
            from service.mcp.mcp_tool_service import MCPToolService

            tools = await MCPToolService.get_instance().list_tools(include_inactive=False)
            for tool in tools:
                _record(tool.get("name"), tool.get("description"))
        except Exception:
            logger.warning("Could not load MCP tool metadata; tool descriptions may be incomplete", exc_info=True)

        try:
            from core.security.mcp.mcp_url_policy import default_mcp_url
            import service.proxy.proxy_service as proxy_service_module

            tools_service_url = default_mcp_url()
            payload = await proxy_service_module.get_proxy_service().get_builtin_mcp_tools(tools_service_url)
            for tool in payload.get("tools", []):
                _record(tool.get("name"), tool.get("description"))
        except Exception:
            logger.warning(
                "Could not load built-in MCP tool metadata; tool descriptions may be incomplete", exc_info=True
            )

        return descriptions

    async def _get_available_mcp_tool_names(self) -> set[str]:
        return set((await self._get_mcp_tool_metadata()).keys())

    async def _fetch_rag_knowledge_selector_payload(self) -> dict[str, Any] | None:
        """Fetch the RAG service's full knowledge-selector payload.

        The endpoint always returns every available collection (it has no
        filter-by-id support), so callers checking many collections/agents
        should fetch this once per request and reuse it rather than calling
        it once per collection lookup.
        """
        base_url = (env.INTERNAL_RAG_SERVICE_API_URL or "").rstrip("/")
        if not base_url:
            return None

        headers: dict[str, str] = {"X-Language": get_locale()}
        token = (env.INTERNAL_SERVICE_TOKEN or "").strip()
        if token:
            headers["X-Internal-Service-Token"] = token

        try:
            response = await outbound.request(
                outbound.RAG_SERVICE,
                "GET",
                f"{base_url}/api/v1/datasources/knowledge-selector",
                timeout=10.0,
                headers=headers,
            )
            if response.status_code != 200:
                return None
            from integrations.rag_client import parse_rag_response_model

            payload = parse_rag_response_model(response.json(), response.status_code)
        except (httpx.HTTPError, json.JSONDecodeError, DependencyResponseError):
            return None

        return payload if isinstance(payload, dict) else None

    def _filter_rag_service_collection_info(
        self,
        collection_ids: list[str],
        *,
        source_key: str,
        payload: dict[str, Any] | None,
    ) -> tuple[set[str], dict[str, str]]:
        if not collection_ids or not payload:
            return set(), {}

        requested = set(collection_ids)
        rows = payload.get(source_key)
        if not isinstance(rows, list):
            return set(), {}

        existing: set[str] = set()
        display_names: dict[str, str] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            collection_id = str(row.get("id") or "")
            if collection_id not in requested:
                continue
            existing.add(collection_id)
            display_name = row.get("name") or collection_id
            display_names[collection_id] = str(display_name)

        return existing, display_names

    async def _get_existing_collection_info(
        self,
        collection_ids: list[str],
        *,
        source_key: str,
        rag_payload: dict[str, Any] | None = None,
        _local_cache: dict[str, dict[str, Any] | None] | None = None,
    ) -> tuple[set[str], dict[str, str]]:
        if not collection_ids:
            return set(), {}
        if rag_payload is None:
            rag_payload = await self._fetch_rag_knowledge_selector_payload()
        return self._filter_rag_service_collection_info(
            collection_ids,
            source_key=source_key,
            payload=rag_payload,
        )

    def _is_memory_available(self) -> bool:
        try:
            from infrastructure.runtime.langgraph_store import get_langgraph_store

            return get_langgraph_store() is not None
        except Exception:
            return False

    async def _get_agent_availability(
        self,
        agent: dict[str, Any],
        *,
        available_models: set[str] | None = None,
        available_mcp_tools: set[str] | None = None,
        memory_available: bool | None = None,
        rag_payload: dict[str, Any] | None = None,
        local_collection_cache: dict[str, dict[str, Any] | None] | None = None,
    ) -> dict[str, Any]:
        """Compute an agent's real availability.

        `available_models`/`available_mcp_tools`/`memory_available`/
        `rag_payload` are environment-wide (not agent-specific), and
        `local_collection_cache` memoizes local DB lookups by collection id.
        Callers checking many agents at once (e.g. the catalog list) should
        fetch/create these once and pass them in here to avoid redundant
        lookups per agent.
        """
        rag_config = agent.get("rag_config") or {}
        document_collections = [str(c) for c in rag_config.get("document_processing") or []]
        graph_collections = [str(c) for c in rag_config.get("knowledge_graph") or []]

        if available_models is None:
            available_models = await self._get_available_model_names()
        if available_mcp_tools is None:
            available_mcp_tools = await self._get_available_mcp_tool_names()
        if memory_available is None:
            memory_available = self._is_memory_available()
        if rag_payload is None and (document_collections or graph_collections):
            rag_payload = await self._fetch_rag_knowledge_selector_payload()

        available_rag_collections, rag_display_names = await self._get_existing_collection_info(
            document_collections,
            source_key="document_processing",
            rag_payload=rag_payload,
            _local_cache=local_collection_cache,
        )
        (
            available_graph_rag_collections,
            graph_display_names,
        ) = await self._get_existing_collection_info(
            graph_collections,
            source_key="knowledge_graph",
            rag_payload=rag_payload,
            _local_cache=local_collection_cache,
        )
        collection_display_names = {**rag_display_names, **graph_display_names}

        return build_agent_availability(
            agent,
            available_models=available_models,
            default_model=env.DEFAULT_MODEL,
            available_mcp_tools=available_mcp_tools,
            available_rag_collections=available_rag_collections,
            available_graph_rag_collections=available_graph_rag_collections,
            collection_display_names=collection_display_names,
            memory_available=memory_available,
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

    async def _serialize_builtin_persona_summary(
        self,
        persona_id: int,
        name: str,
        description: str,
        base_agent: str,
        *,
        available_models: set[str] | None = None,
        available_mcp_tools: set[str] | None = None,
        memory_available: bool | None = None,
        rag_payload: dict[str, Any] | None = None,
        local_collection_cache: dict[str, dict[str, Any] | None] | None = None,
    ) -> dict[str, Any]:
        serialized = {
            "id": persona_id,
            "external_id": None,
            "name": name,
            "description": description,
            "uploaded_image_id": None,
            "icon_name": None,
            "is_public": True,
            "is_visible": True,
            "display_priority": None,
            "featured": False,
            "builtin_persona": True,
            "is_dynamic": False,
            "labels": [],
            "owner": {"id": "system", "email": "System"},
            "base_agent": base_agent,
            "tools": [],
            "starter_messages": None,
            "document_sets": [],
            "hierarchy_node_count": 0,
            "attached_document_count": 0,
            "knowledge_sources": [],
            "llm_model_version_override": None,
            "llm_model_provider_override": None,
            "mcp_tools": [],
            "action_count": 0,
            "memory_type": "none",
            "long_term_memory": False,
            "capabilities": {
                "has_actions": False,
                "has_conversation_starters": False,
                "has_retrieval": False,
                "has_web_search": False,
                "has_scoped_knowledge": False,
                "long_term_memory": False,
            },
        }
        serialized["availability"] = await self._get_agent_availability(
            serialized,
            available_models=available_models,
            available_mcp_tools=available_mcp_tools,
            memory_available=memory_available,
            rag_payload=rag_payload,
            local_collection_cache=local_collection_cache,
        )
        return serialized

    async def _serialize_custom_persona_summary(
        self,
        persona: dict[str, Any],
        owner_emails: dict[str, str] | None = None,
        *,
        available_models: set[str] | None = None,
        available_mcp_tools: set[str] | None = None,
        memory_available: bool | None = None,
        rag_payload: dict[str, Any] | None = None,
        local_collection_cache: dict[str, dict[str, Any] | None] | None = None,
        tool_descriptions: dict[str, dict[str, str]] | None = None,
        dynamic_defs_by_persona_id: dict[int, Any] | None = None,
        flow_summaries: dict[Any, Any] | None = None,
    ) -> dict[str, Any]:
        label_ids = persona.get("labels") or []
        labels = [label if isinstance(label, dict) else {"id": label, "name": f"Label {label}"} for label in label_ids]
        mcp_tools = persona.get("mcp_tools") or []
        if tool_descriptions is None and mcp_tools:
            tool_descriptions = await self._get_mcp_tool_metadata()
        rag_config = persona.get("rag_config") or {
            "document_processing": [],
            "knowledge_graph": [],
        }
        document_collections = rag_config.get("document_processing") or []
        graph_collections = rag_config.get("knowledge_graph") or []
        has_scoped_knowledge = bool(
            document_collections
            or graph_collections
            or persona.get("document_sets")
            or persona.get("hierarchy_nodes")
            or persona.get("attached_documents")
            or persona.get("user_file_ids")
        )
        has_retrieval = bool(has_scoped_knowledge or "search" in mcp_tools)
        long_term_memory = bool(persona.get("long_term_memory", False))
        dynamic_def = (
            dynamic_defs_by_persona_id.get(int(persona["id"]))
            if dynamic_defs_by_persona_id and "id" in persona and persona["id"] is not None
            else None
        )
        graph_schema = dynamic_def.graph_schema if dynamic_def else persona.get("graph_schema")
        agent_definition_id = (
            str(dynamic_def.id)
            if dynamic_def
            else (str(persona["agent_definition_id"]) if persona.get("agent_definition_id") else None)
        )
        is_dynamic = (
            persona.get("base_agent") == "dynamic-agent" or bool(dynamic_def) or bool(persona.get("is_dynamic"))
        )
        serialized = {
            "id": persona["id"],
            "external_id": persona.get("external_id"),
            "name": persona["name"],
            "description": persona["description"],
            "uploaded_image_id": persona.get("uploaded_image_id"),
            "icon_name": persona.get("icon_name"),
            "is_public": persona.get("is_public", True),
            "is_visible": True,
            "display_priority": persona.get("display_priority"),
            "featured": bool(persona.get("featured", False)),
            "builtin_persona": False,
            "is_dynamic": is_dynamic,
            "labels": labels,
            "owner": {
                "id": str(persona.get("user_id") or DEFAULT_USER_ID),
                "email": self._resolve_owner_email(persona, owner_emails),
            },
            "base_agent": persona.get("base_agent"),
            "tools": self._build_tool_snapshots(
                persona["id"],
                mcp_tools,
                rag_config,
                tool_descriptions=tool_descriptions,
            ),
            "starter_messages": persona.get("starter_messages"),
            "document_sets": [],
            "hierarchy_node_count": 0,
            "attached_document_count": 0,
            "knowledge_sources": [],
            "llm_model_version_override": persona.get("llm_model_version_override"),
            "llm_model_provider_override": persona.get("llm_model_provider_override"),
            "mcp_tools": mcp_tools,
            "rag_config": rag_config,
            "connector_bindings": persona.get("connector_bindings") or [],
            "action_count": len(mcp_tools),
            "memory_type": "long_term" if long_term_memory else persona.get("memory_type"),
            "long_term_memory": long_term_memory,
            "capabilities": {
                "has_actions": len(mcp_tools) > 0,
                "has_conversation_starters": bool(persona.get("starter_messages")),
                "has_retrieval": has_retrieval,
                "has_web_search": _has_web_search_tool(mcp_tools),
                "has_scoped_knowledge": has_scoped_knowledge,
                "long_term_memory": long_term_memory,
            },
        }
        if graph_schema:
            serialized["graph_schema"] = graph_schema
        if agent_definition_id:
            serialized["agent_definition_id"] = agent_definition_id
        serialized.update(flow_meta_fields(dynamic_def, flow_summaries))
        serialized["availability"] = await self._get_agent_availability(
            serialized,
            available_models=available_models,
            available_mcp_tools=available_mcp_tools,
            memory_available=memory_available,
            rag_payload=rag_payload,
            local_collection_cache=local_collection_cache,
        )
        return serialized

    async def _serialize_custom_persona(
        self,
        persona: dict[str, Any],
        owner_emails: dict[str, str] | None = None,
        *,
        user: AuthenticatedUser | None = None,
        tool_descriptions: dict[str, dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        if owner_emails is None:
            owner_emails = await self._load_owner_emails([persona], current_user=user)

        label_ids = persona.get("labels") or []
        labels = [label if isinstance(label, dict) else {"id": label, "name": f"Label {label}"} for label in label_ids]
        mcp_tools = persona.get("mcp_tools") or []
        if tool_descriptions is None and mcp_tools:
            tool_descriptions = await self._get_mcp_tool_metadata()
        mcp_tool_configs = persona.get("mcp_tool_configs") or {}
        rag_config = persona.get("rag_config") or {
            "document_processing": [],
            "knowledge_graph": [],
        }

        serialized = {
            "id": persona["id"],
            "name": persona["name"],
            "description": persona["description"],
            "tools": self._build_tool_snapshots(
                persona["id"],
                mcp_tools,
                rag_config,
                tool_descriptions=tool_descriptions,
            ),
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
                "email": self._resolve_owner_email(persona, owner_emails),
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
            "mcp_tool_configs": mcp_tool_configs,
            "rag_config": rag_config,
            "connector_bindings": persona.get("connector_bindings") or [],
            "long_term_memory": bool(persona.get("long_term_memory", False)),
            "search_start_date": persona.get("search_start_date"),
        }
        if persona.get("base_agent") == "dynamic-agent":
            definition = await self._get_dynamic_definition(int(persona["id"]))
            summaries: dict[Any, Any] = {}
            if definition is not None and definition.graph_schema == "flow":
                summaries = await flow_version_repository().get_summaries([definition.id])
            self._merge_dynamic_definition(serialized, definition, flow_summaries=summaries)
        serialized["availability"] = await self._get_agent_availability(serialized)
        return serialized

    async def authorize_agent_execution(self, agent_id: str, user: AuthenticatedUser) -> None:
        """Authorize generic invoke/stream IDs before loading stored configuration."""
        from service.personas.constants import AGENT_TO_PERSONA_ID

        if agent_id in AGENT_TO_PERSONA_ID:
            return
        await self.authorize_chat_persona(agent_id, user)

    async def authorize_chat_persona(self, persona_id: Any, user: AuthenticatedUser) -> int:
        """Resolve the saved persona and authorize it before chat side effects."""
        if persona_id is None:
            return 0
        try:
            resolved_id = int(persona_id)
        except (ValueError, TypeError):
            try:
                definition_id = uuid.UUID(str(persona_id))
            except ValueError:
                self._raise_not_found("persona.not_found")
            definition = await agent_definition_repository().get_by_id(definition_id)
            if not definition or not definition.is_active or definition.persona_id is None:
                self._raise_not_found("persona.not_found")
            resolved_id = definition.persona_id
        if resolved_id in (0, 1):
            return resolved_id
        user = await self._resolve_access_user(user)
        persona = await persona_repository().get(resolved_id)
        if not persona:
            self._raise_not_found("persona.not_found")
        restricted, accessible = await self._load_agent_group_visibility(user)
        can_manage = await self._can_manage_all_personas(user)
        if not self._can_access_persona(persona, user, restricted, accessible, can_manage):
            self._raise_not_found("persona.not_found")
        return resolved_id

    async def get_persona(
        self,
        persona_id: int,
        user: AuthenticatedUser | None = None,
    ) -> dict[str, Any]:
        if user:
            user = await self._resolve_access_user(user)

        builtin_display = {
            0: ("Chatbot", "chatbot"),
            1: ("Configurable MCP Agent", "configurable-mcp-agent"),
        }

        if persona_id in builtin_display:
            display_name, base_agent = builtin_display[persona_id]
            from agents.registry.registry import agents as all_agents

            description = all_agents[base_agent].description if base_agent in all_agents else ""
            return await self._serialize_builtin_persona(persona_id, display_name, description, base_agent)

        persona = await persona_repository().get(persona_id)
        if not persona:
            raise AgentNotFoundError()

        if user:
            (
                restricted_persona_ids,
                accessible_persona_ids,
            ) = await self._load_agent_group_visibility(user)
            can_manage_all_personas = await self._can_manage_all_personas(user)
            if not self._can_access_persona(
                persona,
                user,
                restricted_persona_ids,
                accessible_persona_ids,
                can_manage_all_personas,
            ):
                raise AgentNotFoundError()

        return await self._serialize_custom_persona(persona, user=user)

    async def get_personas(
        self,
        user: AuthenticatedUser | None = None,
    ) -> list[dict[str, Any]]:
        if user:
            user = await self._resolve_access_user(user)

        personas = []

        builtin_display = {
            "chatbot": "Chatbot",
            "configurable-mcp-agent": "Configurable MCP Agent",
        }
        for idx, (agent_key, display_name) in enumerate(builtin_display.items()):
            from agents.registry.registry import agents as all_agents

            description = all_agents[agent_key].description if agent_key in all_agents else ""
            personas.append(await self._serialize_builtin_persona(idx, display_name, description, agent_key))

        try:
            custom_personas = await persona_repository().list_all(include_builtin=False)
            restricted_persona_ids: set[int] = set()
            accessible_persona_ids: set[int] = set()
            can_manage_all_personas = False
            if user:
                (
                    restricted_persona_ids,
                    accessible_persona_ids,
                ) = await self._load_agent_group_visibility(user)
                can_manage_all_personas = await self._can_manage_all_personas(user)
            visible_personas = [
                persona
                for persona in custom_personas
                if not user
                or self._can_access_persona(
                    persona,
                    user,
                    restricted_persona_ids,
                    accessible_persona_ids,
                    can_manage_all_personas,
                )
            ]
            owner_emails = await self._load_owner_emails(visible_personas, current_user=user)
            personas.extend(
                [await self._serialize_custom_persona(persona, owner_emails) for persona in visible_personas]
            )
        except Exception:
            logger.warning("Could not load custom personas; returning partial list", exc_info=True)

        return personas

    async def get_agent_catalog(
        self,
        user: AuthenticatedUser | None = None,
    ) -> list[dict[str, Any]]:
        if user:
            user = await self._resolve_access_user(user)

        agents = []

        # Environment-wide availability inputs are fetched once and reused
        # across every agent in the catalog, instead of re-checking them
        # per agent, so the list can show real availability cheaply. The MCP
        # tool metadata fetch also supplies each tool snapshot's description
        # (shown behind the frontend's per-tool info icon), so the name set
        # used for availability is derived from it rather than fetched again.
        try:
            available_models, mcp_tool_metadata = await asyncio.wait_for(
                asyncio.gather(
                    self._get_available_model_names(),
                    self._get_mcp_tool_metadata(),
                ),
                timeout=CATALOG_AVAILABILITY_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.warning(
                "Agent catalog availability lookup timed out; returning catalog with "
                "dependency availability marked unavailable"
            )
            available_models, mcp_tool_metadata = set(), {}
        available_mcp_tools = set(mcp_tool_metadata.keys())
        memory_available = self._is_memory_available()

        builtin_display = {
            "chatbot": "Chatbot",
            "configurable-mcp-agent": "Configurable MCP Agent",
        }
        for idx, (agent_key, display_name) in enumerate(builtin_display.items()):
            from agents.registry.registry import agents as all_agents

            description = all_agents[agent_key].description if agent_key in all_agents else ""
            agents.append(
                await self._serialize_builtin_persona_summary(
                    idx,
                    display_name,
                    description,
                    agent_key,
                    available_models=available_models,
                    available_mcp_tools=available_mcp_tools,
                    memory_available=memory_available,
                )
            )

        try:
            custom_personas = await persona_repository().list_all(include_builtin=False)
            restricted_persona_ids: set[int] = set()
            accessible_persona_ids: set[int] = set()
            can_manage_all_personas = False
            if user:
                (
                    restricted_persona_ids,
                    accessible_persona_ids,
                ) = await self._load_agent_group_visibility(user)
                can_manage_all_personas = await self._can_manage_all_personas(user)
            visible_personas = [
                persona
                for persona in custom_personas
                if not user
                or self._can_access_persona(
                    persona,
                    user,
                    restricted_persona_ids,
                    accessible_persona_ids,
                    can_manage_all_personas,
                )
            ]
            owner_emails = await self._load_owner_emails(visible_personas, current_user=user)

            # RAG collection membership is agent-specific, but the RAG
            # service always returns its *entire* catalog regardless of
            # what's requested, so it's fetched once here (only if any
            # agent actually references a collection) and reused for every
            # agent's check instead of one HTTP round-trip per agent.
            needs_rag_lookup = any(
                (persona.get("rag_config") or {}).get("document_processing")
                or (persona.get("rag_config") or {}).get("knowledge_graph")
                for persona in visible_personas
            )
            rag_payload = await self._fetch_rag_knowledge_selector_payload() if needs_rag_lookup else None
            local_collection_cache: dict[str, dict[str, Any] | None] = {}

            dynamic_defs_by_persona_id: dict[int, Any] = {}
            try:
                dynamic_defs = await agent_definition_repository().list_all(active_only=False)
                dynamic_defs_by_persona_id = {d.persona_id: d for d in dynamic_defs if d.persona_id is not None}
            except Exception:
                logger.warning(
                    "Could not batch-load agent definitions for persona list; per-persona fields may be incomplete",
                    exc_info=True,
                )

            flow_summaries: dict[Any, Any] = {}
            try:
                flow_definition_ids = [d.id for d in dynamic_defs_by_persona_id.values() if d.graph_schema == "flow"]
                flow_summaries = await flow_version_repository().get_summaries(flow_definition_ids)
            except Exception:
                logger.warning(
                    "Could not batch-load flow version summaries; flow cards will render without version metadata",
                    exc_info=True,
                )

            agents.extend(
                [
                    await self._serialize_custom_persona_summary(
                        persona,
                        owner_emails,
                        available_models=available_models,
                        available_mcp_tools=available_mcp_tools,
                        memory_available=memory_available,
                        rag_payload=rag_payload,
                        local_collection_cache=local_collection_cache,
                        tool_descriptions=mcp_tool_metadata,
                        dynamic_defs_by_persona_id=dynamic_defs_by_persona_id,
                        flow_summaries=flow_summaries,
                    )
                    for persona in visible_personas
                ]
            )
        except Exception:
            logger.exception("Failed to assemble custom persona summaries; returning partial list")

        return agents

    async def get_agent_detail(
        self,
        agent_id: str,
        user: AuthenticatedUser | None = None,
    ) -> dict[str, Any]:
        try:
            persona_id = int(agent_id)
        except (TypeError, ValueError) as exc:
            raise AgentNotFoundError() from exc

        return await self.get_persona(persona_id, user)

    async def get_persona_options(
        self,
        user: AuthenticatedUser,
    ) -> list[dict[str, Any]]:
        """Return lightweight visible persona options for assignment UIs."""
        if user:
            user = await self._resolve_access_user(user)

        from agents.registry.registry import agents as all_agents

        builtin_display = {
            "chatbot": "Chatbot",
            "configurable-mcp-agent": "Configurable MCP Agent",
        }
        options = [
            {
                "id": index,
                "name": display_name,
                "description": (all_agents[agent_key].description if agent_key in all_agents else ""),
            }
            for index, (agent_key, display_name) in enumerate(builtin_display.items())
        ]

        custom_personas = await persona_repository().list_all(include_builtin=False)
        restricted_persona_ids, accessible_persona_ids = await self._load_agent_group_visibility(user)
        can_manage_all_personas = await self._can_manage_all_personas(user)
        options.extend(
            {
                "id": persona["id"],
                "name": persona["name"],
                "description": persona.get("description") or "",
            }
            for persona in custom_personas
            if self._can_access_persona(
                persona,
                user,
                restricted_persona_ids,
                accessible_persona_ids,
                can_manage_all_personas,
            )
        )
        return options

    async def create_persona(
        self,
        payload: dict[str, Any],
        user_id: str | None = None,
        auth_token: str | None = None,
        user: AuthenticatedUser | None = None,
    ) -> dict[str, Any]:
        try:
            rag_config = payload.get("rag_config")
            effective_user_id = user_id
            if user is not None:
                effective_user_id = await self.resolve_owner_user_id(auth_token, user)
            effective_user_id = effective_user_id or DEFAULT_USER_ID
            connector_bindings = await self._validate_connector_bindings(payload, effective_user_id)
            mcp_tools = payload.get("mcp_tools") or []
            mcp_tool_configs = await self._validate_mcp_tool_configs(
                user_id=effective_user_id,
                mcp_tools=mcp_tools,
                mcp_tool_configs=payload.get("mcp_tool_configs") or {},
            )
            persona = await persona_repository().create(
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
                uploaded_image_id=payload.get("uploaded_image_id"),
                icon_name=payload.get("icon_name"),
                base_agent=payload.get("base_agent"),
                mcp_tools=mcp_tools,
                mcp_tool_configs=mcp_tool_configs,
                rag_config=rag_config,
                connector_bindings=connector_bindings,
                long_term_memory=bool(payload.get("long_term_memory", False)),
            )
        except PermissionError as exc:
            raise ForbiddenError(message_key="common.forbidden") from exc
        except ValueError as exc:
            raise BadRequestError(message_key="common.bad_request") from exc
        except ApplicationError:
            raise
        except Exception:
            self._raise_internal_error()

        try:
            await self._upsert_dynamic_definition(payload, persona)
        except Exception:
            await persona_repository().delete(int(persona["id"]))
            self._raise_internal_error()
        return await self._serialize_custom_persona(persona)

    async def update_persona(
        self,
        persona_id: int,
        payload: dict[str, Any],
        user_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            existing = await persona_repository().get(persona_id)
            if existing and existing.get("is_builtin"):
                raise ForbiddenError(message_key="persona.cannot_update_builtin")

            if "connector_bindings" not in payload:
                payload = {
                    **payload,
                    "connector_bindings": (existing or {}).get("connector_bindings") or [],
                }

            rag_config = payload.get("rag_config")
            effective_user_id = user_id or str((existing or {}).get("user_id") or DEFAULT_USER_ID)
            connector_bindings = await self._validate_connector_bindings(payload, effective_user_id)
            mcp_tools = payload.get("mcp_tools") or []
            mcp_tool_configs = await self._validate_mcp_tool_configs(
                user_id=effective_user_id,
                mcp_tools=mcp_tools,
                mcp_tool_configs=payload.get("mcp_tool_configs") or {},
            )
            persona = await persona_repository().update(
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
                # Always both, never one: the picker is a single choice, so
                # sending only the newly-set field would leave the other one
                # behind and the old avatar would keep winning.
                uploaded_image_id=(None if payload.get("remove_image") else payload.get("uploaded_image_id")),
                icon_name=None if payload.get("remove_image") else payload.get("icon_name"),
                base_agent=payload.get("base_agent"),
                mcp_tools=mcp_tools,
                mcp_tool_configs=mcp_tool_configs,
                rag_config=rag_config,
                connector_bindings=connector_bindings,
                long_term_memory=bool(payload.get("long_term_memory", False)),
            )
            if not persona:
                self._raise_not_found("persona.not_found")
        except ApplicationError:
            raise
        except PermissionError as exc:
            raise ForbiddenError(message_key="common.forbidden") from exc
        except ValueError as exc:
            raise BadRequestError(message_key="common.bad_request") from exc
        except Exception:
            self._raise_internal_error()

        await self._upsert_dynamic_definition(payload, persona)
        return await self._serialize_custom_persona(persona)

    async def delete_persona(self, persona_id: int) -> dict[str, bool]:
        try:
            persona = await persona_repository().get(persona_id)
            if persona and persona.get("is_builtin"):
                raise ForbiddenError(message_key="persona.cannot_delete_builtin")
            if persona and persona.get("base_agent") == "dynamic-agent":
                definition = await self._get_dynamic_definition(persona_id)
                if definition:
                    await agent_definition_repository().delete(definition.id)
            await persona_repository().delete(persona_id)
        except ApplicationError:
            raise
        except Exception:
            self._raise_internal_error()

        return {"success": True}

    async def upload_persona_image(
        self,
        file: UploadedFile,
        user_id: str | None = None,
    ) -> dict[str, str]:
        """Store an avatar image and return the id the frontend renders.

        The returned id is served by ``GET /api/chat/file/{id}`` — the URL
        `buildImgUrl` builds — so the bytes go into the same in-memory store
        that endpoint reads, and into MinIO + the ``document`` table so they
        survive a restart. Mirrors the project-file upload path in
        user_service rather than inventing a second storage scheme.
        """
        content_type = (file.content_type or "").strip() or "application/octet-stream"
        if not content_type.startswith("image/"):
            raise BadRequestError(message_key="persona.image_must_be_an_image")

        raw = await file.read()
        if not raw:
            raise BadRequestError(message_key="persona.image_is_empty")

        file_id = uuid.uuid4().hex
        filename = file.filename or f"{file_id}.img"
        effective_user_id = user_id or DEFAULT_USER_ID

        from service.storage.file_service import mime_to_chat_file_type, store_file

        try:
            store_file(file_id, raw, content_type, filename, owner_id=effective_user_id)
        except ValueError as exc:
            raise PayloadTooLargeError() from exc

        # Durable copy. Best-effort like every other upload path here: a
        # MinIO outage must not block picking a logo, it only costs the
        # image its survival across a restart.
        try:
            from service.storage.minio_service import upload_file as minio_upload

            object_key = minio_upload(
                user_id=effective_user_id,
                file_id=file_id,
                filename=filename,
                data=raw,
                mime_type=content_type,
            )
            await document_repository().create(
                file_id=file_id,
                user_id=effective_user_id,
                filename=filename,
                mime_type=content_type,
                chat_file_type=mime_to_chat_file_type(content_type),
                size_bytes=len(raw),
                minio_object_key=object_key,
            )
        except Exception as exc:
            logger.warning("MinIO/DB persist failed for persona image %s: %s", file_id, exc)

        return {"file_id": file_id, "uploaded_image_id": file_id}

    async def get_persona_labels(self) -> list[Any]:
        return []


_persona_service: PersonaService | None = None


def get_persona_service() -> PersonaService:
    """Get singleton PersonaService."""
    global _persona_service
    if _persona_service is None:
        _persona_service = PersonaService()
    return _persona_service
