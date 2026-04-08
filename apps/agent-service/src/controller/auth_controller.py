"""Auth controller - handles authentication, chat sessions, personas, and user preferences."""

import logging
from typing import Any

from controller.base import BaseController
from core.env import env
from service.CheckpointerService import get_checkpointer
from service.PersonaRepository import PersonaDB
from service.StoreService import (
    add_thread,
    delete_thread_from_store,
    get_thread_from_store,
    list_threads_from_store,
    update_thread_in_store,
)

logger = logging.getLogger(__name__)


# Agent to persona_id mapping
AGENT_TO_PERSONA_ID: dict[str, int] = {
    "chatbot": 0,
    "research-assistant": 1,
    "rag-assistant": 2,
    "graph-rag-assistant": 3,
    "command-agent": 4,
    "bg-task-agent": 5,
    "configurable-mcp-agent": 6,
    "langgraph-supervisor-agent": 7,
    "langgraph-supervisor-hierarchy-agent": 8,
    "interrupt-agent": 9,
    "knowledge-base-agent": 10,
    "github-mcp-agent": 11,
}

PERSONA_ID_TO_AGENT: dict[int, str] = {v: k for k, v in AGENT_TO_PERSONA_ID.items()}

# Mock dev user - replace with real auth in production
USER_ID = "dev-user"


class AuthController(BaseController):
    """Controller for auth, chat sessions, personas, and user preferences.

    Injects:
    - PersonaRepository: for persona/agent management
    - CheckpointerService: for LangGraph checkpointing
    """

    def __init__(self):
        self._user_id = USER_ID

    # =========================================================================
    # Chat Sessions
    # =========================================================================

    async def get_chat_sessions(self) -> dict[str, Any]:
        """Return chat sessions for the current user."""
        try:
            threads = await list_threads_from_store(limit=100, offset=0)

            if not threads:
                return {
                    "sessions": [],
                    "chat_sessions": [],
                    "has_more": False,
                }

            checkpointer = get_checkpointer()

            sessions = []
            for thread in threads:
                thread_id = thread.get("thread_id", "")
                metadata = thread.get("metadata", {}) or {}
                session_name = metadata.get("name", "New Chat")

                if session_name == "New Chat" and checkpointer and thread_id:
                    try:
                        config = {"configurable": {"thread_id": thread_id}}
                        checkpoint_tuple = await checkpointer.aget_tuple(config)
                        if checkpoint_tuple and checkpoint_tuple.checkpoint:
                            values = checkpoint_tuple.checkpoint.get("channel_values", {})
                            messages = values.get("messages", [])

                            for msg in messages:
                                msg_type = getattr(msg, "type", None) or msg.get("type", "")
                                if msg_type in ("human", "user"):
                                    content = getattr(msg, "content", "") or msg.get("content", "")
                                    if isinstance(content, list):
                                        for c in content:
                                            if isinstance(c, dict) and c.get("type") == "text":
                                                session_name = c.get("text", "New Chat")[:50]
                                                break
                                    elif isinstance(content, str) and content:
                                        session_name = content[:50]
                                    break
                    except Exception as e:
                        logger.warning(f"Failed to get session name for {thread_id}: {e}")

                sessions.append(
                    {
                        "id": thread_id,
                        "name": session_name or "New Chat",
                        "description": session_name or "New Chat",
                        "persona_id": metadata.get("persona_id", 0),
                        "time_created": thread.get("created_at"),
                        "time_updated": thread.get("updated_at"),
                        "shared_status": "private",
                        "current_alternate_model": None,
                        "current_temperature_override": None,
                    }
                )

            sessions.sort(key=lambda s: s.get("time_updated") or "", reverse=True)

            return {
                "sessions": sessions,
                "chat_sessions": sessions,
                "has_more": False,
            }
        except Exception as e:
            logger.error(f"Failed to get chat sessions: {e}")
            return {"sessions": [], "chat_sessions": [], "has_more": False}

    async def create_chat_session(self) -> dict[str, Any]:
        """Create a new chat session."""
        import uuid
        from datetime import UTC, datetime

        try:
            session_id = str(uuid.uuid4())
            now = datetime.now(UTC).isoformat()

            await add_thread(
                {
                    "thread_id": session_id,
                    "created_at": now,
                    "updated_at": now,
                    "metadata": {
                        "user_id": self._user_id,
                        "name": "New Chat",
                        "source": "create-chat-session",
                    },
                }
            )
            logger.info(f"Created thread {session_id}")

            return {
                "chat_session_id": session_id,
                "name": "New Chat",
            }
        except Exception as e:
            logger.error(f"Failed to create chat session: {e}")
            import uuid

            return {"chat_session_id": str(uuid.uuid4()), "name": "New Chat"}

    async def get_chat_session(self, chat_session_id: str) -> dict[str, Any]:
        """Get chat session with messages from LangGraph thread state."""
        try:
            thread = await get_thread_from_store(chat_session_id)

            if not thread:
                return {
                    "chat_session_id": chat_session_id,
                    "description": "Chat",
                    "persona_id": 0,
                    "persona_name": "",
                    "messages": [],
                    "time_created": None,
                    "time_updated": None,
                    "shared_status": "private",
                    "current_temperature_override": None,
                    "current_alternate_model": None,
                    "owner_name": None,
                    "packets": [],
                }

            thread_metadata = thread.get("metadata", {}) if thread else {}

            messages = []
            checkpointer = get_checkpointer()

            if checkpointer:
                try:
                    config = {"configurable": {"thread_id": chat_session_id}}
                    checkpoint_tuple = await checkpointer.aget_tuple(config)

                    if checkpoint_tuple and checkpoint_tuple.checkpoint:
                        raw_values = checkpoint_tuple.checkpoint.get("channel_values", {})
                        langgraph_messages = raw_values.get("messages", [])

                        for idx, msg in enumerate(langgraph_messages):
                            msg_type = "user"
                            msg_content = ""

                            if hasattr(msg, "type"):
                                msg_type = "assistant" if msg.type in ("ai", "tool") else "user"
                            elif isinstance(msg, dict):
                                msg_type = (
                                    "assistant" if msg.get("type") in ("ai", "tool") else "user"
                                )

                            if hasattr(msg, "content"):
                                content = msg.content
                            elif isinstance(msg, dict):
                                content = msg.get("content", "")
                            else:
                                content = ""

                            if isinstance(content, str):
                                msg_content = content
                            elif isinstance(content, list):
                                for c in content:
                                    if isinstance(c, dict):
                                        if c.get("type") == "text":
                                            msg_content = c.get("text", "")
                                            break
                                    elif isinstance(c, str):
                                        msg_content = c
                                        break
                            elif isinstance(content, dict):
                                msg_content = content.get("text", "") or str(content)

                            parent_msg_id = idx if idx > 0 else None
                            latest_child_id = idx + 2 if idx < len(langgraph_messages) - 1 else None

                            messages.append(
                                {
                                    "message_id": idx + 1,
                                    "message_type": msg_type,
                                    "research_type": None,
                                    "parent_message": parent_msg_id,
                                    "latest_child_message": latest_child_id,
                                    "message": msg_content,
                                    "rephrased_query": None,
                                    "context_docs": None,
                                    "time_sent": None,
                                    "overridden_model": None,
                                    "alternate_assistant_id": thread_metadata.get("persona_id"),
                                    "chat_session_id": chat_session_id,
                                    "citations": None,
                                    "files": [],
                                    "tool_call": None,
                                    "current_feedback": None,
                                    "processing_duration_seconds": None,
                                    "sub_questions": [],
                                    "comments": None,
                                    "parentMessageId": parent_msg_id,
                                    "refined_answer_improvement": None,
                                    "is_agentic": None,
                                }
                            )

                except Exception as e:
                    logger.error(f"Failed to get messages from checkpointer: {e}")

            session_name = thread_metadata.get("name", "New Chat")
            if session_name == "New Chat" and messages:
                for msg in messages:
                    if msg["message_type"] in ("user", "human") and msg["message"]:
                        session_name = msg["message"][:50]
                        break

            return {
                "chat_session_id": chat_session_id,
                "description": session_name,
                "persona_id": thread_metadata.get("persona_id", 0),
                "persona_name": "",
                "messages": messages,
                "time_created": thread.get("created_at") if thread else None,
                "time_updated": thread.get("updated_at") if thread else None,
                "shared_status": "private",
                "current_temperature_override": None,
                "current_alternate_model": None,
                "owner_name": None,
                "packets": [],
            }
        except Exception as e:
            logger.error(f"Error getting chat session: {e}")
            return {
                "chat_session_id": chat_session_id,
                "description": "Chat",
                "persona_id": 0,
                "persona_name": "",
                "messages": [],
                "time_created": None,
                "time_updated": None,
                "shared_status": "private",
                "current_temperature_override": None,
                "current_alternate_model": None,
                "owner_name": None,
                "packets": [],
            }

    async def delete_chat_session(self, chat_session_id: str) -> dict[str, Any]:
        """Delete a chat session."""
        try:
            await delete_thread_from_store(chat_session_id)
            logger.info(f"Deleted thread {chat_session_id}")
        except Exception as e:
            logger.warning(f"Failed to delete thread: {e}")

        return {"success": True}

    async def rename_chat_session(self, session_id: str, name: str) -> dict[str, Any]:
        """Rename chat session."""
        try:
            thread = await get_thread_from_store(session_id)
            if thread:
                metadata = thread.get("metadata", {}) or {}
                metadata["name"] = name
                await update_thread_in_store(session_id, {"metadata": metadata})
                logger.info(f"Renamed session {session_id} to {name}")

            return {"success": True}
        except Exception as e:
            logger.warning(f"Failed to rename chat session: {e}")
            return {"success": True}

    async def update_chat_session_model(self, session_id: str, model: str) -> dict[str, Any]:
        """Update chat session model."""
        try:
            thread = await get_thread_from_store(session_id)
            if thread:
                metadata = thread.get("metadata", {}) or {}
                metadata["current_alternate_model"] = model
                await update_thread_in_store(session_id, {"metadata": metadata})

            return {"success": True}
        except Exception as e:
            logger.warning(f"Failed to update chat session model: {e}")
            return {"success": True}

    async def update_chat_session_temperature(
        self, session_id: str, temperature: float
    ) -> dict[str, Any]:
        """Update chat session temperature."""
        try:
            thread = await get_thread_from_store(session_id)
            if thread:
                metadata = thread.get("metadata", {}) or {}
                metadata["current_temperature_override"] = temperature
                await update_thread_in_store(session_id, {"metadata": metadata})

            return {"success": True}
        except Exception as e:
            logger.warning(f"Failed to update chat session temperature: {e}")
            return {"success": True}

    # =========================================================================
    # Personas
    # =========================================================================

    async def get_personas(self) -> list[dict[str, Any]]:
        """Get all personas/agents - built-in agents + custom from DB."""
        from agents import get_all_agent_info

        personas = []
        agents = get_all_agent_info()

        for i, agent in enumerate(agents):
            persona_id = AGENT_TO_PERSONA_ID.get(agent.key, i)
            personas.append(
                {
                    "id": persona_id,
                    "name": agent.key.replace("-", " ").title(),
                    "description": agent.description,
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
                        "owner": {
                            "id": persona.get("user_id", self._user_id),
                            "email": "dev@local.dev",
                        },
                        "base_agent": persona.get("base_agent"),
                        "mcp_tools": persona.get("mcp_tools", []),
                    }
                )
        except Exception:
            pass

        return personas

    async def create_persona(
        self,
        name: str,
        description: str,
        system_prompt: str = "",
        task_prompt: str = "",
        datetime_aware: bool = True,
        is_public: bool = True,
        llm_model_provider_override: str | None = None,
        llm_model_version_override: str | None = None,
        starter_messages: list | None = None,
        label_ids: list = None,
        base_agent: str | None = None,
        mcp_tools: list[str] = None,
    ) -> dict[str, Any]:
        """Create a new persona/agent."""
        try:
            persona = await PersonaDB.create(
                name=name,
                description=description,
                system_prompt=system_prompt,
                task_prompt=task_prompt,
                user_id=self._user_id,
                is_builtin=False,
                datetime_aware=datetime_aware,
                is_public=is_public,
                llm_model_provider_override=llm_model_provider_override,
                llm_model_version_override=llm_model_version_override,
                starter_messages=starter_messages,
                labels=label_ids or [],
                base_agent=base_agent,
                mcp_tools=mcp_tools or [],
            )
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
                "owner": {"id": self._user_id, "email": "dev@local.dev"},
                "base_agent": persona.get("base_agent"),
                "mcp_tools": persona.get("mcp_tools", []),
            }
        except Exception as e:
            return {"error": str(e)}, 500

    async def update_persona(
        self,
        persona_id: int,
        name: str,
        description: str,
        system_prompt: str = "",
        task_prompt: str = "",
        datetime_aware: bool = True,
        is_public: bool = True,
        llm_model_provider_override: str | None = None,
        llm_model_version_override: str | None = None,
        starter_messages: list | None = None,
        label_ids: list = None,
        base_agent: str | None = None,
        mcp_tools: list[str] = None,
    ) -> dict[str, Any]:
        """Update an existing persona/agent."""
        try:
            existing = await PersonaDB.get(persona_id)
            if existing and existing.get("is_builtin"):
                return {"error": "Cannot update built-in agents"}, 403

            persona = await PersonaDB.update(
                persona_id,
                name=name,
                description=description,
                system_prompt=system_prompt,
                task_prompt=task_prompt,
                datetime_aware=datetime_aware,
                is_public=is_public,
                llm_model_provider_override=llm_model_provider_override,
                llm_model_version_override=llm_model_version_override,
                starter_messages=starter_messages,
                labels=label_ids or [],
                base_agent=base_agent,
                mcp_tools=mcp_tools or [],
            )
            if persona:
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
                    "owner": {"id": self._user_id, "email": "dev@local.dev"},
                    "base_agent": persona.get("base_agent"),
                    "mcp_tools": persona.get("mcp_tools", []),
                }
            return {"error": "Persona not found"}, 404
        except Exception as e:
            return {"error": str(e)}, 500

    async def delete_persona(self, persona_id: int) -> dict[str, Any]:
        """Delete a persona/agent."""
        try:
            persona = await PersonaDB.get(persona_id)
            if persona and persona.get("is_builtin"):
                return {"error": "Cannot delete built-in agents"}, 403
            await PersonaDB.delete(persona_id)
        except Exception as e:
            return {"error": str(e)}, 500
        return {"success": True}

    # =========================================================================
    # LLM Providers
    # =========================================================================

    async def get_llm_providers(self) -> dict[str, Any]:
        """Return LLM provider with dynamically discovered models."""
        from core.providers.registry import provider_registry

        provider_registry.initialize()
        provider_infos = await provider_registry.get_provider_infos()

        providers = []
        for i, info in enumerate(provider_infos):
            model_configs = [
                {
                    "name": m.name,
                    "is_visible": m.is_visible,
                    "max_input_tokens": m.max_input_tokens,
                    "supports_image_input": m.supports_image_input,
                    "supports_reasoning": m.supports_reasoning,
                }
                for m in info.models
            ]
            providers.append(
                {
                    "id": i + 1,
                    "name": info.name,
                    "provider": info.provider_type,
                    "provider_display_name": info.display_name,
                    "model_configurations": model_configs,
                }
            )

        default_model = env.DEFAULT_MODEL or None
        if not default_model and provider_infos:
            for info in provider_infos:
                if info.is_available and info.models:
                    default_model = info.models[0].name
                    break

        return {
            "providers": providers,
            "selected_provider": providers[0]["name"] if providers else None,
            "default_text": default_model,
            "default_vision": None,
        }

    async def get_llm_built_in_options(self) -> list[dict[str, Any]]:
        """Return built-in LLM options from available providers."""
        from core.providers.registry import provider_registry

        provider_registry.initialize()
        provider_infos = await provider_registry.get_provider_infos()

        result = []
        for info in provider_infos:
            for model in info.models:
                result.append(
                    {
                        "name": model.name,
                        "is_visible": model.is_visible,
                        "max_input_tokens": model.max_input_tokens,
                        "supports_image_input": model.supports_image_input,
                        "supports_reasoning": model.supports_reasoning,
                        "provider": info.name,
                    }
                )

        return result

    async def get_ollama_models(self) -> list[dict[str, Any]]:
        """Get available Ollama models from the actual Ollama server."""
        from core.providers.ollama import OllamaProvider

        provider = OllamaProvider()
        models = await provider.get_available_models()
        return [{"name": m.name, "display_name": m.display_name} for m in models]


# Singleton instance
_auth_controller: AuthController | None = None


def get_auth_controller() -> AuthController:
    """Get the singleton AuthController instance."""
    global _auth_controller
    if _auth_controller is None:
        _auth_controller = AuthController()
    return _auth_controller
