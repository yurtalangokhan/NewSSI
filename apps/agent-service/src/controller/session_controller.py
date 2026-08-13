"""Session, persona, and LLM provider controller."""

import logging
import re
from typing import Any

from i18n import t

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

USER_ID = "dev-user"


class SessionController(BaseController):
    """Controller for chat sessions, personas, and LLM providers."""

    def __init__(self):
        self._user_id = USER_ID

    async def get_chat_sessions(self) -> dict[str, Any]:
        try:
            threads = await list_threads_from_store(limit=100, offset=0)

            if not threads:
                return {"sessions": [], "chat_sessions": [], "has_more": False}

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

            return {"sessions": sessions, "chat_sessions": sessions, "has_more": False}
        except Exception as e:
            logger.error(f"Failed to get chat sessions: {e}")
            return {"sessions": [], "chat_sessions": [], "has_more": False}

    async def create_chat_session(self) -> dict[str, Any]:
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

            return {"chat_session_id": session_id, "name": "New Chat"}
        except Exception as e:
            logger.error(f"Failed to create chat session: {e}")
            import uuid

            return {"chat_session_id": str(uuid.uuid4()), "name": "New Chat"}

    async def get_chat_session(self, chat_session_id: str) -> dict[str, Any]:
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
            packets_2d: list[list[dict]] = []
            checkpointer = get_checkpointer()

            if checkpointer:
                try:
                    config = {"configurable": {"thread_id": chat_session_id}}
                    checkpoint_tuple = await checkpointer.aget_tuple(config)

                    if checkpoint_tuple and checkpoint_tuple.checkpoint:
                        raw_values = checkpoint_tuple.checkpoint.get("channel_values", {})
                        langgraph_messages = raw_values.get("messages", [])

                        def _strip_think_tags(text: str) -> str:
                            if not text:
                                return text
                            result = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
                            result = re.sub(
                                r"<thinking>.*?</thinking>", "", result, flags=re.DOTALL
                            )
                            result = re.sub(
                                r"<think>(?:(?!</think>).)*$", "", result, flags=re.DOTALL
                            )
                            result = re.sub(
                                r"<thinking>(?:(?!</thinking>).)*$", "", result, flags=re.DOTALL
                            )
                            return result.strip()

                        def _extract_content(msg) -> str:
                            if hasattr(msg, "content"):
                                content = msg.content
                            elif isinstance(msg, dict):
                                content = msg.get("content", "")
                            else:
                                return ""
                            if isinstance(content, str):
                                return content
                            elif isinstance(content, list):
                                for c in content:
                                    if isinstance(c, dict) and c.get("type") == "text":
                                        return c.get("text", "")
                                    elif isinstance(c, str):
                                        return c
                            elif isinstance(content, dict):
                                return content.get("text", "") or str(content)
                            return ""

                        pending_tool_packets: list[dict] = []
                        msg_idx = 0

                        for raw_msg in langgraph_messages:
                            raw_type = getattr(raw_msg, "type", None)
                            if raw_type is None and isinstance(raw_msg, dict):
                                raw_type = raw_msg.get("type", "")

                            if raw_type == "tool":
                                tool_name = getattr(raw_msg, "name", "") or ""
                                tool_content = _extract_content(raw_msg)
                                pending_tool_packets.append(
                                    {
                                        "placement": {"turn_index": 0, "sub_turn_index": None},
                                        "obj": {
                                            "type": "custom_tool_delta",
                                            "tool_name": tool_name,
                                            "response_type": "tool_result",
                                            "data": tool_content,
                                        },
                                    }
                                )
                                continue

                            if raw_type == "ai":
                                tool_calls = getattr(raw_msg, "tool_calls", None) or []
                                msg_content = _strip_think_tags(_extract_content(raw_msg))

                                if tool_calls:
                                    for tc in tool_calls:
                                        tc_name = (
                                            tc.get("name", "tool")
                                            if isinstance(tc, dict)
                                            else getattr(tc, "name", "tool")
                                        )
                                        tc_args = (
                                            tc.get("args")
                                            if isinstance(tc, dict)
                                            else getattr(tc, "args", None)
                                        )
                                        pending_tool_packets.append(
                                            {
                                                "placement": {
                                                    "turn_index": 0,
                                                    "sub_turn_index": None,
                                                },
                                                "obj": {
                                                    "type": "custom_tool_start",
                                                    "tool_name": tc_name,
                                                    "args": tc_args,
                                                },
                                            }
                                        )
                                    continue

                                turn_packets = []
                                if pending_tool_packets:
                                    turn_packets.extend(pending_tool_packets)
                                    pending_tool_packets = []
                                display_turn = 1 if turn_packets else 0
                                turn_packets.append(
                                    {
                                        "placement": {
                                            "turn_index": display_turn,
                                            "sub_turn_index": None,
                                        },
                                        "obj": {
                                            "type": "message_start",
                                            "content": msg_content,
                                            "final_documents": None,
                                        },
                                    }
                                )
                                turn_packets.append(
                                    {
                                        "placement": {
                                            "turn_index": display_turn,
                                            "sub_turn_index": None,
                                        },
                                        "obj": {
                                            "type": "stop",
                                            "stop_reason": "finished",
                                        },
                                    }
                                )
                                packets_2d.append(turn_packets)

                                parent_msg_id = msg_idx if msg_idx > 0 else None
                                msg_idx += 1

                                messages.append(
                                    {
                                        "message_id": msg_idx,
                                        "message_type": "assistant",
                                        "research_type": None,
                                        "parent_message": parent_msg_id,
                                        "latest_child_message": None,
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
                                continue

                            msg_content = _strip_think_tags(_extract_content(raw_msg))
                            parent_msg_id = msg_idx if msg_idx > 0 else None
                            msg_idx += 1

                            if isinstance(raw_msg, dict):
                                _extra = raw_msg.get("additional_kwargs", {}) or {}
                            else:
                                _extra = getattr(raw_msg, "additional_kwargs", {}) or {}
                            raw_files_meta = _extra.get("files_metadata", [])
                            history_files = [
                                {
                                    "id": f.get("id", ""),
                                    "type": f.get("type", "document"),
                                    "name": f.get("name"),
                                }
                                for f in (raw_files_meta or [])
                                if isinstance(f, dict) and f.get("id")
                            ]

                            messages.append(
                                {
                                    "message_id": msg_idx,
                                    "message_type": "user",
                                    "research_type": None,
                                    "parent_message": parent_msg_id,
                                    "latest_child_message": None,
                                    "message": msg_content,
                                    "rephrased_query": None,
                                    "context_docs": None,
                                    "time_sent": None,
                                    "overridden_model": None,
                                    "alternate_assistant_id": thread_metadata.get("persona_id"),
                                    "chat_session_id": chat_session_id,
                                    "citations": None,
                                    "files": history_files,
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

                        for i in range(len(messages) - 1):
                            messages[i]["latest_child_message"] = messages[i + 1]["message_id"]

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
                "packets": packets_2d,
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
        try:
            await delete_thread_from_store(chat_session_id)
            logger.info(f"Deleted thread {chat_session_id}")
        except Exception as e:
            logger.warning(f"Failed to delete thread: {e}")
        return {"success": True}

    async def rename_chat_session(self, session_id: str, name: str) -> dict[str, Any]:
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

    async def get_personas(self) -> list[dict[str, Any]]:
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
        try:
            existing = await PersonaDB.get(persona_id)
            if existing and existing.get("is_builtin"):
                return {"error": t("persona.cannot_update_builtin")}, 403

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
            return {"error": t("persona.not_found")}, 404
        except Exception as e:
            return {"error": str(e)}, 500

    async def delete_persona(self, persona_id: int) -> dict[str, Any]:
        try:
            persona = await PersonaDB.get(persona_id)
            if persona and persona.get("is_builtin"):
                return {"error": t("persona.cannot_delete_builtin")}, 403
            await PersonaDB.delete(persona_id)
        except Exception as e:
            return {"error": str(e)}, 500
        return {"success": True}

    async def get_llm_providers(self) -> dict[str, Any]:
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
        from core.providers.ollama import OllamaProvider

        provider = OllamaProvider()
        models = await provider.get_available_models()
        return [{"name": m.name, "display_name": m.display_name} for m in models]


_session_controller: SessionController | None = None


def get_session_controller() -> SessionController:
    global _session_controller
    if _session_controller is None:
        _session_controller = SessionController()
    return _session_controller
