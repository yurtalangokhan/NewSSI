"""
Auth routes - provides endpoints needed by the Onyx frontend.
Integrates with backend agents and uses PostgreSQL for persistence.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents import get_all_agent_info, DEFAULT_AGENT
from core import settings
from schema.schema import StreamInput
from service.agent_routes import message_generator
from service.checkpointer import get_checkpointer
from service.store import (
    add_thread,
    get_thread_from_store,
    list_threads_from_store,
    update_thread_in_store,
    delete_thread_from_store,
)
from service.persona_db import PersonaDB

router = APIRouter(prefix="", tags=["auth"])

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


def _get_user_id(request: Request | None = None) -> str:
    """Get user ID from request or use mock dev user."""
    return USER_ID


def _truncate_name(message: str, max_length: int = 50) -> str:
    """Truncate message to use as session name."""
    # Clean up the message
    name = message.strip()
    # Remove extra whitespace
    name = " ".join(name.split())
    # Truncate if too long
    if len(name) > max_length:
        name = name[:max_length].rsplit(" ", 1)[0] + "..."
    return name or "New Chat"


class User(BaseModel):
    id: str = "dev-user-1"
    email: str = "dev@local.dev"
    is_active: bool = True
    is_superuser: bool = True
    is_verified: bool = True
    role: str = "admin"
    preferences: dict = {
        "chosen_assistants": None,
        "visible_assistants": [],
        "hidden_assistants": [],
        "default_model": None,
        "recent_assistants": [],
        "auto_scroll": True,
        "shortcut_enabled": True,
        "temperature_override_enabled": False,
        "theme_preference": None,
        "chat_background": None,
        "default_app_mode": "AUTO",
    }
    team_name: str | None = None
    is_anonymous_user: bool = False
    password_configured: bool = True


class AuthTypeMetadata(BaseModel):
    authType: str = "basic"
    autoRedirect: bool = False
    requiresVerification: bool = False
    anonymousUserEnabled: bool = False
    passwordMinLength: int = 8
    hasUsers: bool = True
    oauthEnabled: bool = False


class Settings(BaseModel):
    auto_scroll: bool = True
    application_status: str = "active"
    gpu_enabled: bool = False
    maximum_chat_retention_days: str | None = None
    notifications: list = []
    needs_reindexing: bool = False
    anonymous_user_enabled: bool = False
    invite_only_enabled: bool = False
    deep_research_enabled: bool = True
    temperature_override_enabled: bool = True
    query_history_type: str = "normal"


class CombinedSettings(BaseModel):
    settings: Settings = Settings()
    enterpriseSettings: str | None = None
    customAnalyticsScript: str | None = None
    webVersion: str = "dev"
    webDomain: str = "http://localhost:3000"
    product: str = "Agentic AI"


# =============================================================================
# Auth Endpoints
# =============================================================================


@router.get("/auth/type")
async def get_auth_type() -> AuthTypeMetadata:
    """Return auth type metadata."""
    return AuthTypeMetadata()


@router.get("/me")
async def get_current_user() -> User:
    """Return current user (dev mode - always returns mock user)."""
    return User()


@router.post("/auth/login")
async def login(response: Response):
    """Login endpoint - returns success in dev mode."""
    response.set_cookie("session", "dev-session", httponly=True, samesite="lax")
    return {"success": True, "user_id": "dev-user-1"}


@router.post("/auth/logout")
async def logout(response: Response):
    """Logout endpoint."""
    response.delete_cookie("session")
    return {"success": True}


@router.get("/settings")
async def get_settings() -> Settings:
    """Return settings."""
    return Settings()


@router.get("/enterprise-settings")
async def get_enterprise_settings() -> dict:
    """Return enterprise settings."""
    return {"application_name": "Agentic AI", "use_custom_logo": False}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# =============================================================================
# Chat Session Endpoints
# =============================================================================


@router.get("/api/chat/get-user-chat-sessions")
async def get_chat_sessions():
    """
    Return chat sessions for the current user.
    Fetches from LangGraph's thread store and enriches with message content.
    Compatible with the frontend's expected format.
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        from service.store import list_threads_from_store

        # Fetch all threads
        threads = await list_threads_from_store(limit=100, offset=0)

        if not threads:
            return {
                "sessions": [],
                "chat_sessions": [],
                "has_more": False,
            }

        # Enrich threads with first message content from checkpoint
        checkpointer = get_checkpointer()

        sessions = []
        for thread in threads:
            thread_id = thread.get("thread_id", "")
            metadata = thread.get("metadata", {}) or {}
            session_name = metadata.get("name", "New Chat")

            # Try to get first message from checkpoint if name is "New Chat"
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

        # Sort by most recent first
        sessions.sort(key=lambda s: s.get("time_updated") or "", reverse=True)

        return {
            "sessions": sessions,
            "chat_sessions": sessions,
            "has_more": False,
        }
    except Exception as e:
        logger.error(f"Failed to get chat sessions: {e}")
        import traceback

        traceback.print_exc()
        return {"sessions": [], "chat_sessions": [], "has_more": False}


@router.post("/api/chat/create-chat-session")
async def create_chat_session():
    """Create a new chat session using Thread-based storage."""
    import logging

    logger = logging.getLogger(__name__)

    try:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Create thread in LangGraph store (single source of truth)
        await add_thread(
            {
                "thread_id": session_id,
                "created_at": now,
                "updated_at": now,
                "metadata": {
                    "user_id": USER_ID,
                    "name": "New Chat",
                    "source": "create-chat-session",
                },
            }
        )
        logger.info(f"Created thread {session_id} in LangGraph store")

        return {
            "chat_session_id": session_id,
            "name": "New Chat",
        }
    except Exception as e:
        logger.error(f"Failed to create chat session: {e}")
        import traceback

        traceback.print_exc()
        return {"chat_session_id": str(uuid.uuid4()), "name": "New Chat"}


@router.get("/api/chat/get-chat-session/{chat_session_id}")
async def get_chat_session(chat_session_id: str):
    """
    Get chat session with messages from LangGraph thread state.

    Uses Thread-based storage as the single source of truth.
    """
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"[get-chat-session] Starting for {chat_session_id}")

    try:
        # Get thread metadata from store
        thread = await get_thread_from_store(chat_session_id)
        logger.info(f"[get-chat-session] Thread: {thread}")

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

        # Get messages from LangGraph checkpointer
        messages = []
        checkpointer = get_checkpointer()
        logger.info(f"[get-chat-session] Checkpointer: {type(checkpointer)}")

        if checkpointer:
            try:
                config = {"configurable": {"thread_id": chat_session_id}}
                checkpoint_tuple = await checkpointer.aget_tuple(config)

                if checkpoint_tuple and checkpoint_tuple.checkpoint:
                    raw_values = checkpoint_tuple.checkpoint.get("channel_values", {})
                    langgraph_messages = raw_values.get("messages", [])
                    logger.info(
                        f"[get-chat-session] Found {len(langgraph_messages)} messages in checkpoint"
                    )

                    # Convert LangGraph messages to frontend-compatible format
                    for idx, msg in enumerate(langgraph_messages):
                        msg_type = "user"
                        msg_content = ""

                        # Determine message type
                        if hasattr(msg, "type"):
                            msg_type = "assistant" if msg.type in ("ai", "tool") else "user"
                        elif isinstance(msg, dict):
                            msg_type = "assistant" if msg.get("type") in ("ai", "tool") else "user"

                        # Extract content
                        if hasattr(msg, "content"):
                            content = msg.content
                        elif isinstance(msg, dict):
                            content = msg.get("content", "")
                        else:
                            content = ""

                        # Parse content
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

                        # Calculate parent/child relationships
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
                                "files": [],  # Required field - empty array by default
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
                logger.error(f"[get-chat-session] Failed to get messages from checkpointer: {e}")

        # Get session name from metadata or first message
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
        logger.error(f"[get-chat-session] Error: {e}", exc_info=True)
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


@router.post("/api/chat/delete-chat-session/{chat_session_id}")
async def delete_chat_session(chat_session_id: str):
    """Delete chat session using Thread-based storage."""
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Delete thread from LangGraph store
        await delete_thread_from_store(chat_session_id)
        logger.info(f"Deleted thread {chat_session_id}")
    except Exception as e:
        logger.warning(f"Failed to delete thread: {e}")

    return {"success": True}


@router.post("/api/chat/delete-all-chat-sessions")
async def delete_all_chat_sessions():
    """Delete all chat sessions for the current user using Thread-based storage."""
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Get all threads for this user
        threads = await list_threads_from_store(limit=1000, offset=0, metadata={"user_id": USER_ID})

        for thread in threads:
            thread_id = thread.get("thread_id")
            if thread_id:
                try:
                    await delete_thread_from_store(thread_id)
                except Exception as e:
                    logger.warning(f"Failed to delete thread {thread_id}: {e}")

        logger.info(f"Deleted all chat sessions for user {USER_ID}")
    except Exception as e:
        logger.warning(f"Failed to delete all chat sessions: {e}")

    return {"success": True}


@router.put("/api/chat/rename-chat-session")
async def rename_chat_session(request: Request):
    """Rename chat session using Thread-based storage."""
    import logging

    logger = logging.getLogger(__name__)

    try:
        body = await request.json()
        session_id = body.get("chat_session_id")
        name = body.get("name")

        if session_id and name is not None:
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


@router.put("/api/chat/update-chat-session-model")
async def update_chat_session_model(request: Request):
    """Update chat session model using Thread-based storage."""
    import logging

    logger = logging.getLogger(__name__)

    try:
        body = await request.json()
        session_id = body.get("chat_session_id")
        model = body.get("model")

        if session_id and model:
            thread = await get_thread_from_store(session_id)
            if thread:
                metadata = thread.get("metadata", {}) or {}
                metadata["current_alternate_model"] = model
                await update_thread_in_store(session_id, {"metadata": metadata})

        return {"success": True}
    except Exception as e:
        logger.warning(f"Failed to update chat session model: {e}")
        return {"success": True}


@router.put("/api/chat/update-chat-session-temperature")
async def update_chat_session_temperature(request: Request):
    """Update chat session temperature using Thread-based storage."""
    import logging

    logger = logging.getLogger(__name__)

    try:
        body = await request.json()
        session_id = body.get("chat_session_id")
        temperature = body.get("temperature")

        if session_id and temperature is not None:
            thread = await get_thread_from_store(session_id)
            if thread:
                metadata = thread.get("metadata", {}) or {}
                metadata["current_temperature_override"] = temperature
                await update_thread_in_store(session_id, {"metadata": metadata})

        return {"success": True}
    except Exception as e:
        logger.warning(f"Failed to update chat session temperature: {e}")
        return {"success": True}


@router.post("/api/chat/stop-chat-session/{chat_session_id}")
async def stop_chat_session(chat_session_id: str):
    """Stop chat session."""
    return {"success": True}


@router.put("/api/chat/set-message-as-latest")
async def set_message_as_latest():
    """Set message as latest."""
    return {"success": True}


@router.get("/api/chat/available-context-tokens")
async def get_available_context_tokens():
    """Return available context tokens."""
    return {"max_tokens": 120000, "selected_tokens": 120000}


# =============================================================================
# Chat Message Endpoints
# =============================================================================


@router.post("/api/chat/create-chat-message-feedback")
async def create_chat_message_feedback():
    """Create chat message feedback."""
    return {"success": True}


@router.delete("/api/chat/remove-chat-message-feedback")
async def remove_chat_message_feedback():
    """Remove chat message feedback."""
    return {"success": True}


@router.get("/api/chat/available-context-tokens/{session_id}")
async def get_available_context_tokens_for_session(session_id: str):
    """Return available context tokens for a session."""
    return {"max_tokens": 120000, "selected_tokens": 120000}


@router.get("/user/projects/session/{session_id}/token-count")
async def get_session_token_count(session_id: str):
    """Return token count for session."""
    return {"token_count": 0}


@router.get("/user/projects/session/{session_id}/files")
async def get_session_files(session_id: str):
    """Return files for session."""
    return {"files": []}


class ChatMessageInput(BaseModel):
    message: str
    chat_session_id: str | None = None
    persona_id: int | None = None
    parent_message_id: str | None = None
    file_descriptors: list[str] = []
    internal_search_filters: dict[str, Any] = {}
    deep_research: bool = False
    allowed_tool_ids: list[int] = []
    forced_tool_id: int | None = None
    llm_override: dict[str, Any] | None = None
    origin: str = "unknown"
    additional_context: str | None = None
    message_id_to_resend: int | None = None


@router.post("/api/chat/send-chat-message")
async def send_chat_message(request: Request, message_input: ChatMessageInput):
    """
    Send chat message with streaming response.

    This endpoint uses Thread-based storage as the single source of truth:
    1. Creates/updates thread in LangGraph store
    2. Streams the AI response
    """
    import logging

    logger = logging.getLogger(__name__)

    # Generate new session_id if not provided or invalid
    session_id = message_input.chat_session_id
    if not session_id:
        session_id = str(uuid.uuid4())
        logger.info(f"Generated new session_id: {session_id}")

    # Validate UUID format
    try:
        uuid.UUID(session_id)
    except (ValueError, AttributeError):
        session_id = str(uuid.uuid4())
        logger.warning(f"Invalid session_id provided, generated new: {session_id}")

    session_name = _truncate_name(message_input.message)

    # Ensure thread exists in LangGraph store (single source of truth)
    try:
        thread = await get_thread_from_store(session_id)
        if not thread:
            now = datetime.now(timezone.utc).isoformat()
            await add_thread(
                {
                    "thread_id": session_id,
                    "created_at": now,
                    "updated_at": now,
                    "metadata": {
                        "user_id": USER_ID,
                        "name": session_name,
                        "persona_id": message_input.persona_id,
                    },
                }
            )
            logger.info(f"Created thread {session_id} in store")
        else:
            # Update thread metadata if needed
            metadata = thread.get("metadata", {}) or {}
            needs_update = False
            if metadata.get("name") in (None, "", "New Chat"):
                metadata["name"] = session_name
                needs_update = True
            if (
                message_input.persona_id is not None
                and metadata.get("persona_id") != message_input.persona_id
            ):
                metadata["persona_id"] = message_input.persona_id
                needs_update = True
            if needs_update:
                await update_thread_in_store(session_id, {"metadata": metadata})
                logger.info(f"Updated thread {session_id}")
    except Exception as e:
        logger.warning(f"Failed to manage thread in store: {e}")

    # Determine which agent to use
    agent_key = DEFAULT_AGENT
    if message_input.persona_id is not None:
        agent_key = PERSONA_ID_TO_AGENT.get(message_input.persona_id, DEFAULT_AGENT)

    stream_input = StreamInput(
        message=message_input.message,
        thread_id=session_id,
        agent_config=message_input.llm_override or {},
    )

    async def generate_stream():
        """Generate streaming response."""
        full_response = ""
        try:
            async for chunk in message_generator(stream_input, agent_key, USER_ID):
                yield chunk

                # Parse and accumulate for final storage
                if isinstance(chunk, str) and "data:" in chunk:
                    try:
                        data_str = chunk.replace("data:", "").strip()
                        if data_str and data_str != "[DONE]":
                            data = json.loads(data_str)
                            if data.get("type") == "token":
                                full_response += data.get("content", "")
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f'data: {{"type": "error", "content": "{str(e)}"}}\n\n'
            full_response = f"Error: {str(e)}"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# =============================================================================
# Persona/Agent Endpoints
# =============================================================================


@router.get("/api/persona")
async def get_personas():
    """Get all personas/agents - built-in agents + custom from DB."""
    personas = []
    agents = get_all_agent_info()

    # Built-in agents
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

    # Custom personas from DB
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
                }
            )
    except Exception:
        pass

    return personas


class PersonaUpsertRequest(BaseModel):
    name: str
    description: str
    system_prompt: str = ""
    task_prompt: str = ""
    datetime_aware: bool = True
    document_set_ids: list = []
    is_public: bool = True
    llm_model_provider_override: str | None = None
    llm_model_version_override: str | None = None
    starter_messages: list | None = None
    users: list = []
    groups: list = []
    tool_ids: list = []
    remove_image: bool = False
    uploaded_image_id: str | None = None
    icon_name: str | None = None
    search_start_date: str | None = None
    featured: bool = False
    display_priority: int | None = None
    label_ids: list = []
    user_file_ids: list = []
    replace_base_system_prompt: bool = False
    hierarchy_node_ids: list = []
    document_ids: list = []


@router.post("/api/persona")
async def create_persona(request: PersonaUpsertRequest):
    """Create a new persona/agent."""
    try:
        persona = await PersonaDB.create(
            name=request.name,
            description=request.description,
            system_prompt=request.system_prompt,
            task_prompt=request.task_prompt,
            user_id=USER_ID,
            is_builtin=False,
            datetime_aware=request.datetime_aware,
            is_public=request.is_public,
            llm_model_provider_override=request.llm_model_provider_override,
            llm_model_version_override=request.llm_model_version_override,
            starter_messages=request.starter_messages,
            labels=request.label_ids,
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
            "owner": {"id": USER_ID, "email": "dev@local.dev"},
        }
    except Exception as e:
        return {"error": str(e)}, 500


@router.patch("/api/persona/{persona_id}")
async def update_persona(persona_id: int, request: PersonaUpsertRequest):
    """Update an existing persona/agent."""
    try:
        persona = await PersonaDB.update(
            persona_id,
            name=request.name,
            description=request.description,
            system_prompt=request.system_prompt,
            task_prompt=request.task_prompt,
            datetime_aware=request.datetime_aware,
            is_public=request.is_public,
            llm_model_provider_override=request.llm_model_provider_override,
            llm_model_version_override=request.llm_model_version_override,
            starter_messages=request.starter_messages,
            labels=request.label_ids,
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
                "owner": {"id": USER_ID, "email": "dev@local.dev"},
            }
        return {"error": "Persona not found"}, 404
    except Exception as e:
        return {"error": str(e)}, 500


@router.delete("/api/persona/{persona_id}")
async def delete_persona(persona_id: int):
    """Delete a persona/agent."""
    try:
        await PersonaDB.delete(persona_id)
    except Exception:
        pass
    return {"success": True}


@router.post("/api/admin/persona/upload-image")
async def upload_persona_image():
    """Upload persona image (mock)."""
    return {"file_id": "mock-image-id"}


# =============================================================================
# LLM/Admin Endpoints
# =============================================================================


@router.get("/api/llm/provider")
async def get_llm_provider():
    """Return LLM provider."""
    return {"providers": [], "selected_provider": None}


@router.get("/api/user/assistant/preferences")
async def get_user_assistant_preferences():
    """Return user assistant preferences."""
    return {}


@router.get("/api/admin/llm/built-in/options")
async def get_llm_built_in_options():
    """Return built-in LLM options."""
    models = list(settings.AVAILABLE_MODELS)
    model_configs = []
    for model in models:
        model_configs.append(
            {
                "name": model,
                "is_visible": True,
                "max_input_tokens": None,
                "supports_image_input": False,
                "supports_reasoning": False,
            }
        )

    return [
        {
            "name": "ollama",
            "known_models": model_configs,
            "recommended_default_model": {
                "name": settings.DEFAULT_MODEL,
                "display_name": settings.DEFAULT_MODEL,
            },
        }
    ]


@router.post("/api/admin/llm/test/default")
async def test_llm_default():
    """Test default LLM."""
    return {"success": True}


@router.get("/api/user/files/recent")
async def get_recent_files():
    """Return recent files."""
    return []


@router.post("/api/auth/refresh")
async def refresh_auth():
    """Refresh auth."""
    return {"success": True}


@router.get("/api/admin/default-assistant")
async def get_default_assistant():
    """Return default assistant."""
    return None


@router.get("/api/user/projects")
async def get_user_projects():
    """Return user projects."""
    return []


@router.get("/api/notifications")
async def get_notifications():
    """Return notifications."""
    return []


@router.get("/api/input_prompt")
async def get_input_prompts():
    """Return input prompts."""
    return []


@router.get("/api/manage/connector-status")
async def get_connector_status():
    """Return connector status."""
    return []


@router.get("/api/federated/oauth-status")
async def get_federated_oauth_status():
    """Return federated OAuth status."""
    return {"enabled": False}


@router.get("/api/federated")
async def get_federated():
    """Return federated connectors."""
    return []


@router.get("/api/query/valid-tags")
async def get_valid_tags():
    """Return valid query tags."""
    return []


@router.get("/api/manage/document-set")
async def get_document_sets():
    """Return document sets."""
    return []


@router.get("/admin/llm/provider")
async def get_admin_llm_provider():
    """Get LLM provider info."""
    models = list(settings.AVAILABLE_MODELS)
    model_configs = []
    for model in models:
        model_configs.append(
            {
                "name": model,
                "is_visible": True,
                "max_input_tokens": None,
                "supports_image_input": False,
                "supports_reasoning": False,
            }
        )

    return {
        "providers": [
            {
                "id": 1,
                "name": "ollama",
                "provider": "ollama",
                "provider_display_name": "Ollama",
                "api_key": None,
                "api_base": None,
                "api_version": None,
                "custom_config": {},
                "is_public": True,
                "is_auto_mode": False,
                "groups": [],
                "personas": [],
                "deployment_name": None,
                "model_configurations": model_configs,
            }
        ],
        "selected_provider": "ollama",
    }


@router.post("/api/admin/llm/test")
async def test_llm():
    """Test LLM connection."""
    return {"success": True}


@router.post("/api/admin/llm/default")
async def set_default_llm():
    """Set default LLM model."""
    return {"success": True}


@router.get("/api/admin/llm/ollama/available-models")
async def get_ollama_models():
    """Get available Ollama models."""
    models = list(settings.AVAILABLE_MODELS)
    return [{"name": m, "display_name": m} for m in models]


@router.put("/api/admin/llm/provider")
async def save_llm_provider():
    """Save LLM provider."""
    return {"success": True}


@router.post("/api/admin/llm/provider")
async def create_llm_provider():
    """Create LLM provider."""
    return {"success": True}


@router.get("/llm/persona/{persona_id}/providers")
async def get_persona_providers(persona_id: int):
    """Get providers for a specific persona."""
    models = list(settings.AVAILABLE_MODELS)
    model_configs = []
    for model in models:
        model_configs.append(
            {
                "name": model,
                "is_visible": True,
                "max_input_tokens": None,
                "supports_image_input": False,
                "supports_reasoning": False,
            }
        )

    return {
        "providers": [
            {
                "id": 1,
                "name": "ollama",
                "provider": "ollama",
                "provider_display_name": "Ollama",
                "model_configurations": model_configs,
            }
        ],
        "selected_provider": settings.DEFAULT_MODEL,
    }


# =============================================================================
# User Preferences Endpoints
# =============================================================================


class PinnedAssistantsUpdate(BaseModel):
    ordered_assistant_ids: list[int] = []


@router.patch("/api/user/pinned-assistants")
async def update_pinned_assistants(request: Request, update: PinnedAssistantsUpdate):
    """Update user's pinned assistants."""
    # In dev mode, we just return success
    # In production, this would update the user's preferences in the database
    return {"success": True, "pinned_assistants": update.ordered_assistant_ids}


@router.get("/api/user/pinned-assistants")
async def get_pinned_assistants():
    """Get user's pinned assistants."""
    # Return default pinned assistants for dev mode
    return {"pinned_assistants": []}


# =============================================================================
# Thread CRUD Operations (maps to LangGraph threads)
# =============================================================================


@router.delete("/api/chat/delete-all-chat-sessions")
async def delete_all_chat_sessions():
    """Delete all chat sessions (threads) for the current user."""
    import logging

    logger = logging.getLogger(__name__)

    try:
        from service.store import list_threads_from_store, delete_thread_from_store

        # Get all threads
        threads = await list_threads_from_store(limit=1000, offset=0)

        deleted_count = 0
        for thread in threads:
            thread_id = thread.get("thread_id")
            if thread_id:
                try:
                    # Delete from thread store
                    await delete_thread_from_store(thread_id)
                    # Note: The checkpointer data will remain until GC runs
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete thread {thread_id}: {e}")

        logger.info(f"Deleted {deleted_count} chat sessions")
        return {"success": True, "deleted_count": deleted_count}
    except Exception as e:
        logger.error(f"Failed to delete all chat sessions: {e}")
        return {"success": False, "error": str(e)}


@router.delete("/api/chat/delete-chat-session/{chat_session_id}")
async def delete_chat_session_v2(chat_session_id: str):
    """Delete a chat session using Thread-based storage."""
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Delete from thread store (single source of truth)
        result = await delete_thread_from_store(chat_session_id)
        logger.info(f"Deleted chat session {chat_session_id}: {result}")
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to delete chat session {chat_session_id}: {e}")
        return {"success": False, "error": str(e)}


@router.patch("/api/chat/rename-chat-session")
async def rename_chat_session_v2(request: Request):
    """Rename chat session using Thread-based storage."""
    import logging

    logger = logging.getLogger(__name__)

    try:
        body = await request.json()
        session_id = body.get("chat_session_id")
        name = body.get("name")

        if not session_id or name is None:
            return {"success": False, "error": "Missing session_id or name"}

        # Update thread metadata (single source of truth)
        result = await update_thread_in_store(
            session_id, {"metadata": {"name": name, "renamed": True}}
        )

        logger.info(f"Renamed chat session {session_id} to '{name}'")
        return {"success": True, "session": result}
    except Exception as e:
        logger.error(f"Failed to rename chat session: {e}")
        return {"success": False, "error": str(e)}
