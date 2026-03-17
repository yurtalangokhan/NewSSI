"""
Auth routes - provides endpoints needed by the Onyx frontend.
These are minimal implementations to allow the frontend to load.
"""

import uuid
from typing import Any, Optional
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from service.agent_routes import message_generator
from schema.schema import StreamInput

router = APIRouter(prefix="", tags=["auth"])


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


# Chat endpoints
@router.get("/api/chat/get-user-chat-sessions")
async def get_chat_sessions():
    """Return chat sessions."""
    return {"chat_sessions": [], "sessions": []}


@router.post("/api/chat/create-chat-session")
async def create_chat_session_v1():
    """Create a new chat session."""
    return {"chat_session_id": "new-session-1", "name": "New Chat"}


# User endpoints
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


# Additional endpoints the frontend might need
@router.get("/api/admin/default-assistant")
async def get_default_assistant():
    """Return default assistant."""
    return None


@router.get("/api/chat/available-context-tokens")
async def get_available_context_tokens():
    """Return available context tokens."""
    return {"max_tokens": 120000, "selected_tokens": 120000}


@router.post("/api/chat/create-chat-session")
async def create_new_chat_session():
    """Create a new chat session."""
    import uuid

    return {"chat_session_id": str(uuid.uuid4()), "name": "New Chat"}


@router.put("/api/chat/rename-chat-session")
async def rename_chat_session():
    """Rename chat session."""
    return {"success": True}


@router.put("/api/chat/set-message-as-latest")
async def set_message_as_latest():
    """Set message as latest."""
    return {"success": True}


@router.post("/api/chat/create-chat-message-feedback")
async def create_chat_message_feedback():
    """Create chat message feedback."""
    return {"success": True}


@router.delete("/api/chat/remove-chat-message-feedback")
async def remove_chat_message_feedback():
    """Remove chat message feedback."""
    return {"success": True}


@router.post("/api/chat/stop-chat-session/{chat_session_id}")
async def stop_chat_session(chat_session_id: str):
    """Stop chat session."""
    return {"success": True}


@router.get("/api/chat/get-chat-session/{chat_session_id}")
async def get_chat_session(chat_session_id: str):
    """Get chat session."""
    return {
        "chat_session_id": chat_session_id,
        "name": "Chat",
        "messages": [],
    }


@router.post("/api/chat/delete-chat-session/{chat_session_id}")
async def delete_chat_session(chat_session_id: str):
    """Delete chat session."""
    return {"success": True}


@router.post("/api/chat/delete-all-chat-sessions")
async def delete_all_chat_sessions():
    """Delete all chat sessions."""
    return {"success": True}


@router.put("/api/chat/update-chat-session-model")
async def update_chat_session_model():
    """Update chat session model."""
    return {"success": True}


@router.put("/api/chat/update-chat-session-temperature")
async def update_chat_session_temperature():
    """Update chat session temperature."""
    return {"success": True}


# =============================================================================
# Persona/Agent endpoints - map from backend /info
# =============================================================================

from agents import get_all_agent_info


class MinimalPersonaSnapshot(BaseModel):
    id: int
    name: str
    description: str
    tools: list = []
    starter_messages: list | None = None
    document_sets: list = []
    is_public: bool = True
    is_visible: bool = True
    display_priority: int | None = None
    featured: bool = False
    builtin_persona: bool = False
    labels: list = []
    owner: dict | None = None


@router.get("/api/persona")
async def get_personas():
    """Get all personas/agents - maps from backend agent info."""
    agents = get_all_agent_info()

    personas = []
    for i, agent in enumerate(agents):
        personas.append(
            {
                "id": i,
                "name": agent.key,
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
                "owner": None,
            }
        )

    # Add custom agents
    personas.extend(custom_agents)

    return personas


class PersonaUpsertRequest(BaseModel):
    name: str
    description: str
    system_prompt: str
    task_prompt: str
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


# In-memory storage for custom agents (for demo purposes)
custom_agents: list = []
next_agent_id = 1000


@router.post("/api/persona")
async def create_persona(request: PersonaUpsertRequest):
    """Create a new persona/agent."""
    global next_agent_id

    agent = {
        "id": next_agent_id,
        "name": request.name,
        "description": request.description,
        "system_prompt": request.system_prompt,
        "task_prompt": request.task_prompt,
        "tools": [],
        "starter_messages": request.starter_messages,
        "document_sets": [],
        "is_public": request.is_public,
        "is_visible": True,
        "display_priority": request.display_priority,
        "featured": request.featured,
        "builtin_persona": False,
        "labels": request.label_ids,
        "owner": {"id": "dev-user", "email": "dev@local.dev"},
        "datetime_aware": request.datetime_aware,
        "llm_model_provider_override": request.llm_model_provider_override,
        "llm_model_version_override": request.llm_model_version_override,
    }

    custom_agents.append(agent)
    next_agent_id += 1

    return agent


@router.patch("/api/persona/{persona_id}")
async def update_persona(persona_id: int, request: PersonaUpsertRequest):
    """Update an existing persona/agent."""
    for agent in custom_agents:
        if agent["id"] == persona_id:
            agent["name"] = request.name
            agent["description"] = request.description
            agent["system_prompt"] = request.system_prompt
            agent["task_prompt"] = request.task_prompt
            agent["is_public"] = request.is_public
            agent["featured"] = request.featured
            agent["llm_model_provider_override"] = request.llm_model_provider_override
            agent["llm_model_version_override"] = request.llm_model_version_override
            agent["starter_messages"] = request.starter_messages
            return agent

    return {"error": "Persona not found"}, 404


@router.delete("/api/persona/{persona_id}")
async def delete_persona(persona_id: int):
    """Delete a persona/agent."""
    global custom_agents
    custom_agents = [a for a in custom_agents if a["id"] != persona_id]
    return {"success": True}


@router.post("/api/admin/persona/upload-image")
async def upload_persona_image():
    """Upload persona image (mock)."""
    return {"file_id": "mock-image-id"}


# =============================================================================
# Chat session endpoints
# =============================================================================


@router.get("/api/chat/get-user-chat-sessions")
async def get_user_chat_sessions():
    """Get user's chat sessions."""
    return {
        "sessions": [],
        "chat_sessions": [],
        "has_more": False,
    }


@router.post("/api/chat/create-chat-session")
async def create_chat_session():
    """Create a new chat session."""
    session_id = str(uuid.uuid4())
    return {
        "chat_session_id": session_id,
        "name": "New Chat",
    }


class ChatMessageInput(BaseModel):
    message: str
    chat_session_id: str
    parent_message_id: str | None = None
    file_descriptors: list = []
    internal_search_filters: dict = {}
    deep_research: bool = False
    allowed_tool_ids: list = []
    forced_tool_id: int | None = None
    llm_override: dict | None = None
    origin: str = "unknown"
    additional_context: str | None = None


@router.post("/api/chat/send-chat-message")
async def send_chat_message(request: Request, message_input: ChatMessageInput):
    """Send chat message - proxies to /stream endpoint."""
    stream_input = StreamInput(
        message=message_input.message,
        thread_id=message_input.chat_session_id,
        agent_config=message_input.llm_override or {},
    )

    return StreamingResponse(
        message_generator(stream_input, "default", "dev-user"),
        media_type="text/event-stream",
    )


# =============================================================================
# LLM/Admin endpoints
# =============================================================================

from core import settings


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


# End of file
