"""
Auth routes - provides endpoints needed by the Onyx frontend.
Integrates with backend agents and uses PostgreSQL for persistence.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents import DEFAULT_AGENT, get_all_agent_info
from controller import AuthController, get_auth_controller
from core import settings
from core.env import env
from schema.schema import StreamInput
from api.routes.AgentsRoute import message_generator
from service.CheckpointerService import get_checkpointer
from service.PersonaRepository import PersonaDB
from service.StoreService import (
    add_thread,
    delete_thread_from_store,
    get_thread_from_store,
    list_threads_from_store,
    update_thread_in_store,
)

router = APIRouter(tags=["auth"])


def _get_controller() -> AuthController:
    """Get the singleton AuthController instance."""
    return get_auth_controller()

# Built-in agent to fixed persona_id mapping (these are not stored in DB)
AGENT_TO_PERSONA_ID: dict[str, int] = {
    "chatbot": 0,
    "configurable-mcp-agent": 1,
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
async def login(request: Request, response: Response):
    """Login endpoint - accepts username and password form data."""
    try:
        # Handle form data or JSON
        content_type = request.headers.get("content-type", "")
        
        if "application/x-www-form-urlencoded" in content_type:
            body = await request.form()
            username = body.get("username", "")
            password = body.get("password", "")
        else:
            body = await request.json()
            username = body.get("username", "")
            password = body.get("password", "")
        
        # In dev mode, accept any credentials
        if username and password:
            response.set_cookie("session", "dev-session", httponly=True, samesite="lax")
            return {
                "success": True,
                "user_id": "dev-user-1",
                "email": f"{username}@example.com"
            }
        else:
            response.status_code = 400
            return {"success": False, "error": "Missing credentials"}
    except Exception as e:
        logger.error(f"Login error: {e}")
        response.status_code = 500
        return {"success": False, "error": str(e)}


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
    ctrl = _get_controller()
    return await ctrl.get_chat_sessions()


@router.post("/api/chat/create-chat-session")
async def create_chat_session():
    """Create a new chat session using Thread-based storage."""
    ctrl = _get_controller()
    return await ctrl.create_chat_session()


@router.get("/api/chat/get-chat-session/{chat_session_id}")
async def get_chat_session(chat_session_id: str):
    """
    Get chat session with messages from LangGraph thread state.

    Uses Thread-based storage as the single source of truth.
    """
    ctrl = _get_controller()
    return await ctrl.get_chat_session(chat_session_id)


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
    model_config = {"extra": "allow"}

    message: str | None = None
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
async def send_chat_message(request: Request):
    """
    Send chat message with streaming response.

    This endpoint uses Thread-based storage as the single source of truth:
    1. Creates/updates thread in LangGraph store
    2. Streams the AI response

    Uses raw JSON parsing to avoid Pydantic validation issues with old sessions.
    """
    import logging

    logger = logging.getLogger(__name__)

    # Parse body manually - bypass Pydantic validation
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse request body: {e}")
        return StreamingResponse(
            iter([b"data: {'type': 'error', 'content': 'Invalid JSON'}\n\n"]),
            media_type="text/event-stream",
        )

    # Extract fields with defaults - handle any edge cases
    message = body.get("message") if body.get("message") is not None else ""
    chat_session_id = body.get("chat_session_id")
    persona_id = body.get("persona_id")
    parent_message_id = body.get("parent_message_id")
    file_descriptors = body.get("file_descriptors", [])
    internal_search_filters = body.get("internal_search_filters", {})
    deep_research = body.get("deep_research", False)
    allowed_tool_ids = body.get("allowed_tool_ids", [])
    forced_tool_id = body.get("forced_tool_id")
    llm_override = body.get("llm_override")
    origin = body.get("origin", "unknown")
    additional_context = body.get("additional_context")
    message_id_to_resend = body.get("message_id_to_resend")

    # Generate new session_id if not provided or invalid
    session_id = chat_session_id
    if not session_id:
        session_id = str(uuid.uuid4())
        logger.info(f"Generated new session_id: {session_id}")

    # Validate UUID format
    try:
        uuid.UUID(session_id)
    except (ValueError, AttributeError):
        session_id = str(uuid.uuid4())
        logger.warning(f"Invalid session_id provided, generated new: {session_id}")

    session_name = _truncate_name(message or "New Chat")

    # Ensure thread exists in LangGraph store (single source of truth)
    try:
        thread = await get_thread_from_store(session_id)
        if not thread:
            now = datetime.now(UTC).isoformat()
            await add_thread(
                {
                    "thread_id": session_id,
                    "created_at": now,
                    "updated_at": now,
                    "metadata": {
                        "user_id": USER_ID,
                        "name": session_name,
                        "persona_id": persona_id,
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
            if persona_id is not None and metadata.get("persona_id") != persona_id:
                metadata["persona_id"] = persona_id
                needs_update = True
            if needs_update:
                await update_thread_in_store(session_id, {"metadata": metadata})
                logger.info(f"Updated thread {session_id}")
    except Exception as e:
        logger.warning(f"Failed to manage thread in store: {e}")

    # Determine which agent to use and build agent config from persona
    agent_key = DEFAULT_AGENT
    agent_config: dict = dict(llm_override or {})

    if persona_id is not None:
        # Check custom personas first (DB), then fall back to built-in mapping
        try:
            custom_persona = await PersonaDB.get(persona_id)
        except Exception:
            custom_persona = None

        if custom_persona and not custom_persona.get("is_builtin"):
            # Custom persona: route to its base_agent and inject persona config
            agent_key = custom_persona.get("base_agent") or DEFAULT_AGENT
            # Pass system_prompt and mcp_tools so the agent can configure itself
            if custom_persona.get("system_prompt"):
                agent_config["system_prompt"] = custom_persona["system_prompt"]
            if custom_persona.get("mcp_tools"):
                agent_config["mcp_tools"] = custom_persona["mcp_tools"]
            if custom_persona.get("llm_model_version_override"):
                agent_config.setdefault("model", custom_persona["llm_model_version_override"])
            # Inject rag_config so RAG tools can read collection IDs at invoke time
            if custom_persona.get("rag_config"):
                agent_config["rag_config"] = custom_persona["rag_config"]
                # Ensure the agent key can handle rag_config (configurable-mcp-agent does)
                if agent_key not in ("configurable-mcp-agent",):
                    agent_key = "configurable-mcp-agent"
        else:
            # Built-in persona id → built-in agent key
            agent_key = PERSONA_ID_TO_AGENT.get(persona_id, DEFAULT_AGENT)

    stream_input = StreamInput(
        message=message or "",
        thread_id=session_id,
        agent_config=agent_config,
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

    # Built-in agents (only the two we expose)
    builtin_display = {
        "chatbot": "Chatbot",
        "configurable-mcp-agent": "Configurable MCP Agent",
    }
    for agent_key, display_name in builtin_display.items():
        persona_id = AGENT_TO_PERSONA_ID[agent_key]
        from agents.agents import agents as all_agents
        description = all_agents[agent_key].description if agent_key in all_agents else ""
        personas.append(
            {
                "id": persona_id,
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
                    "base_agent": persona.get("base_agent"),
                    "mcp_tools": persona.get("mcp_tools", []),
                    "rag_config": persona.get("rag_config"),
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
    # For custom agents: which base agent to use (chatbot, configurable-mcp-agent)
    base_agent: str | None = None
    # For custom agents: list of MCP tool names to bind
    mcp_tools: list[str] = []
    # RAG configuration: {"document_processing": [...uuids], "knowledge_graph": [...uuids]}
    rag_config: dict | None = None


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
            base_agent=request.base_agent,
            mcp_tools=request.mcp_tools if request.mcp_tools else [],
            rag_config=request.rag_config,
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
            "base_agent": persona.get("base_agent"),
            "mcp_tools": persona.get("mcp_tools", []),
            "rag_config": persona.get("rag_config"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/persona/{persona_id}")
async def get_persona(persona_id: int):
    """Get a single persona/agent by ID."""
    try:
        persona = await PersonaDB.get(persona_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")
        return {
            "id": persona["id"],
            "name": persona["name"],
            "description": persona["description"],
            "system_prompt": persona.get("system_prompt", ""),
            "task_prompt": persona.get("task_prompt", ""),
            "tools": [],
            "starter_messages": persona.get("starter_messages"),
            "document_sets": [],
            "is_public": persona.get("is_public", True),
            "is_visible": True,
            "display_priority": None,
            "featured": False,
            "builtin_persona": persona.get("is_builtin", False),
            "labels": persona.get("labels", []),
            "owner": {"id": persona.get("user_id", USER_ID), "email": "dev@local.dev"},
            "base_agent": persona.get("base_agent"),
            "mcp_tools": persona.get("mcp_tools", []),
            "rag_config": persona.get("rag_config"),
            "llm_model_provider_override": persona.get("llm_model_provider_override"),
            "llm_model_version_override": persona.get("llm_model_version_override"),
            "users": [],
            "groups": [],
            "user_file_ids": [],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/api/persona/{persona_id}")
async def update_persona(persona_id: int, request: PersonaUpsertRequest):
    """Update an existing persona/agent."""
    try:
        existing = await PersonaDB.get(persona_id)
        if existing and existing.get("is_builtin"):
            raise HTTPException(status_code=403, detail="Cannot update built-in agents")

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
            base_agent=request.base_agent,
            mcp_tools=request.mcp_tools if request.mcp_tools else [],
            rag_config=request.rag_config,
        )
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")
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
            "rag_config": persona.get("rag_config"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/persona/{persona_id}")
async def delete_persona(persona_id: int):
    """Delete a persona/agent. Cannot delete built-in agents."""
    try:
        persona = await PersonaDB.get(persona_id)
        if persona and persona.get("is_builtin"):
            raise HTTPException(status_code=403, detail="Cannot delete built-in agents")
        await PersonaDB.delete(persona_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True}


@router.post("/api/admin/persona/upload-image")
async def upload_persona_image():
    """Upload persona image (mock)."""
    return {"file_id": "mock-image-id"}


# =============================================================================
# LLM/Admin Endpoints
# =============================================================================


@router.get("/api/llm/persona/{persona_id}/providers")
async def get_persona_llm_providers(persona_id: int):
    """Return LLM providers for a specific persona."""
    return await get_llm_provider()


@router.get("/api/llm/provider")
async def get_llm_provider():
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

    # Determine default model
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


@router.get("/api/user/assistant/preferences")
async def get_user_assistant_preferences():
    """Return user assistant preferences."""
    return {}


@router.get("/api/admin/llm/built-in/options")
async def get_llm_built_in_options():
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
    """Get LLM provider info with dynamically discovered models."""
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
                "api_key": None,
                "api_base": info.base_url,
                "api_version": None,
                "custom_config": {},
                "is_public": True,
                "is_auto_mode": False,
                "groups": [],
                "personas": [],
                "deployment_name": None,
                "model_configurations": model_configs,
            }
        )

    # Determine default model
    default_model = env.DEFAULT_MODEL or None
    if not default_model and provider_infos:
        for info in provider_infos:
            if info.is_available and info.models:
                default_model = info.models[0].name
                break

    return {
        "providers": providers,
        "selected_provider": providers[0]["name"] if providers else None,
        "default_model": default_model,
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
    """Get available Ollama models from the actual Ollama server."""
    from core.providers.ollama import OllamaProvider

    provider = OllamaProvider()
    models = await provider.get_available_models()
    return [{"name": m.name, "display_name": m.display_name} for m in models]


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
    """Get providers for a specific persona with dynamically discovered models."""
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

    # Determine default model
    default_model = env.DEFAULT_MODEL or None
    if not default_model and provider_infos:
        for info in provider_infos:
            if info.is_available and info.models:
                default_model = info.models[0].name
                break

    return {
        "providers": providers,
        "selected_provider": providers[0]["name"] if providers else None,
        "default_model": default_model,
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
        from service.StoreService import delete_thread_from_store, list_threads_from_store

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


# =============================================================================
# MCP Administration Endpoints
# =============================================================================


@router.get("/api/admin/mcp/servers")
async def get_mcp_servers():
    """Get configured MCP servers."""
    import os
    from datetime import datetime

    # Get MCP servers configuration from environment or defaults
    mcp_servers = []

    # Check for tools service MCP server
    tools_service_url = os.getenv("TOOLS_SERVICE_URL", "http://localhost:8003")
    if tools_service_url:
        mcp_servers.append(
            {
                "id": 1,
                "name": "Built-in Tools",
                "description": "Built-in tools service",
                "server_url": tools_service_url,
                "owner": "system",
                "is_authenticated": True,
                "status": "CONNECTED",
                "tool_count": 0,
                "last_refreshed_at": datetime.now().isoformat(),
            }
        )

    # Check for other configured MCP servers
    # Add more MCP servers as needed

    return {"mcp_servers": mcp_servers}
