"""Auth controller - handles authentication, chat sessions, personas, and user preferences."""

import logging
import re
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
            packets_2d: list[list[dict]] = []
            checkpointer = get_checkpointer()

            if checkpointer:
                try:
                    config = {"configurable": {"thread_id": chat_session_id}}
                    checkpoint_tuple = await checkpointer.aget_tuple(config)

                    if checkpoint_tuple and checkpoint_tuple.checkpoint:
                        raw_values = checkpoint_tuple.checkpoint.get("channel_values", {})
                        langgraph_messages = raw_values.get("messages", [])

                        # Helper to strip <think>...</think> tags from content
                        def _strip_think_tags(text: str) -> str:
                            if not text:
                                return text
                            result = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
                            result = re.sub(r"<thinking>.*?</thinking>", "", result, flags=re.DOTALL)
                            # Also strip incomplete opening tags at the end
                            result = re.sub(r"<think>(?:(?!</think>).)*$", "", result, flags=re.DOTALL)
                            result = re.sub(r"<thinking>(?:(?!</thinking>).)*$", "", result, flags=re.DOTALL)
                            return result.strip()

                        # Helper to extract text content from various message formats
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

                        def _extract_reasoning_from_tags(text: str) -> str:
                            if not text:
                                return ""

                            reasoning_parts: list[str] = []
                            for open_tag, close_tag in (("<think>", "</think>"), ("<thinking>", "</thinking>")):
                                start = 0
                                while True:
                                    open_pos = text.find(open_tag, start)
                                    if open_pos == -1:
                                        break

                                    search_from = open_pos + len(open_tag)
                                    close_pos = text.find(close_tag, search_from)
                                    if close_pos == -1:
                                        chunk = text[search_from:]
                                        if chunk.strip():
                                            reasoning_parts.append(chunk.strip())
                                        break

                                    chunk = text[search_from:close_pos]
                                    if chunk.strip():
                                        reasoning_parts.append(chunk.strip())
                                    start = close_pos + len(close_tag)

                            return "\n".join(reasoning_parts).strip()

                        def _extract_visible_and_reasoning(msg) -> tuple[str, str]:
                            if hasattr(msg, "content"):
                                content = msg.content
                            elif isinstance(msg, dict):
                                content = msg.get("content", "")
                            else:
                                return "", ""

                            if isinstance(content, list):
                                visible_parts: list[str] = []
                                reasoning_parts: list[str] = []
                                for item in content:
                                    if isinstance(item, dict):
                                        item_type = item.get("type")
                                        if item_type == "thinking":
                                            thinking_text = str(item.get("thinking", "") or "")
                                            if thinking_text:
                                                reasoning_parts.append(thinking_text)
                                            continue

                                        if item_type == "text":
                                            text = str(item.get("text", "") or "")
                                            if not text:
                                                continue
                                            if item.get("thought"):
                                                reasoning_parts.append(text)
                                            else:
                                                visible_parts.append(text)
                                            continue

                                    if isinstance(item, str) and item:
                                        visible_parts.append(item)

                                visible_text = "".join(visible_parts).strip()
                                reasoning_text = "\n".join(part for part in reasoning_parts if part).strip()
                                return visible_text, reasoning_text

                            text = _extract_content(msg)
                            return _strip_think_tags(text), _extract_reasoning_from_tags(text)

                        def _extract_reasoning_from_metadata(msg) -> str:
                            def _stringify(value: Any) -> str:
                                if isinstance(value, str):
                                    return value.strip()
                                if isinstance(value, list):
                                    parts: list[str] = []
                                    for item in value:
                                        if isinstance(item, str) and item:
                                            parts.append(item)
                                        elif isinstance(item, dict):
                                            text = item.get("text") or item.get("reasoning") or item.get("thinking")
                                            if isinstance(text, str) and text:
                                                parts.append(text)
                                    return "\n".join(parts).strip()
                                return ""

                            def _pick(payload: Any) -> str:
                                if not isinstance(payload, dict):
                                    return ""

                                for key in (
                                    "reasoning_content",
                                    "reasoning",
                                    "thinking",
                                    "reasoning_text",
                                    "thoughts",
                                    "thought",
                                    "chain_of_thought",
                                ):
                                    extracted = _stringify(payload.get(key))
                                    if extracted:
                                        return extracted

                                nested_content = payload.get("content")
                                if isinstance(nested_content, dict):
                                    return _pick(nested_content)

                                return ""

                            if isinstance(msg, dict):
                                additional_kwargs = msg.get("additional_kwargs", {}) or {}
                                response_metadata = msg.get("response_metadata", {}) or {}
                            else:
                                additional_kwargs = getattr(msg, "additional_kwargs", {}) or {}
                                response_metadata = getattr(msg, "response_metadata", {}) or {}

                            return _pick(additional_kwargs) or _pick(response_metadata)

                        # First pass: collect tool call info per AI message for packet reconstruction
                        # pending_tool_packets collects packets for the current assistant turn
                        pending_tool_packets: list[dict] = []
                        msg_idx = 0  # sequential message id counter

                        for raw_msg in langgraph_messages:
                            raw_type = getattr(raw_msg, "type", None)
                            if raw_type is None and isinstance(raw_msg, dict):
                                raw_type = raw_msg.get("type", "")

                            # --- Tool messages: add delta packet, skip as visible message ---
                            if raw_type == "tool":
                                tool_name = getattr(raw_msg, "name", "") or ""
                                tool_content = _extract_content(raw_msg)
                                pending_tool_packets.append({
                                    "placement": {"turn_index": 0, "sub_turn_index": None},
                                    "obj": {
                                        "type": "custom_tool_delta",
                                        "tool_name": tool_name,
                                        "response_type": "tool_result",
                                        "data": tool_content,
                                    },
                                })
                                continue

                            # --- AI messages ---
                            if raw_type == "ai":
                                tool_calls = getattr(raw_msg, "tool_calls", None) or []
                                msg_content, reasoning_text = _extract_visible_and_reasoning(raw_msg)
                                if not reasoning_text:
                                    reasoning_text = _extract_reasoning_from_metadata(raw_msg)

                                if tool_calls:
                                    # AI message that has tool_calls → intermediate step
                                    # Emit tool_start packets and skip as visible message
                                    # (even if it also has content, that content is just
                                    # the model's internal reasoning before calling the tool)
                                    for tc in tool_calls:
                                        tc_name = tc.get("name", "tool") if isinstance(tc, dict) else getattr(tc, "name", "tool")
                                        pending_tool_packets.append({
                                            "placement": {"turn_index": 0, "sub_turn_index": None},
                                            "obj": {
                                                "type": "custom_tool_start",
                                                "tool_name": tc_name,
                                            },
                                        })
                                    continue

                                # AI message with actual content (final answer)
                                # Flush pending tool packets for this assistant turn
                                # and bump turn_index for the display packets
                                turn_packets = []
                                if pending_tool_packets:
                                    turn_packets.extend(pending_tool_packets)
                                    pending_tool_packets = []

                                if reasoning_text:
                                    turn_packets.append({
                                        "placement": {"turn_index": 0, "sub_turn_index": None},
                                        "obj": {"type": "reasoning_start"},
                                    })
                                    turn_packets.append({
                                        "placement": {"turn_index": 0, "sub_turn_index": None},
                                        "obj": {
                                            "type": "reasoning_delta",
                                            "reasoning": reasoning_text,
                                        },
                                    })

                                # Add display packets with a different turn_index
                                display_turn = 1 if turn_packets else 0
                                turn_packets.append({
                                    "placement": {"turn_index": display_turn, "sub_turn_index": None},
                                    "obj": {
                                        "type": "message_start",
                                        "content": msg_content,
                                        "final_documents": None,
                                    },
                                })
                                turn_packets.append({
                                    "placement": {"turn_index": display_turn, "sub_turn_index": None},
                                    "obj": {
                                        "type": "stop",
                                        "stop_reason": "finished",
                                    },
                                })
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

                            # --- Human messages ---
                            msg_content = _strip_think_tags(_extract_content(raw_msg))
                            parent_msg_id = msg_idx if msg_idx > 0 else None
                            msg_idx += 1

                            # Restore file badges from additional_kwargs set at send time.
                            # raw_msg may be a LangChain object or a plain dict depending
                            # on which checkpointer / deserialization path is used.
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

                        # Fix latest_child_message links
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
