"""
Minimal FastAPI server with Ollama support for development.
Provides endpoints needed by the frontend for LLM, agents, and chat.
Run with: python minimal_server.py
"""

import os
import json
import uuid
import asyncio
from datetime import datetime
from typing import Optional

import httpx
from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Agentic AI Backend (Ollama)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

chat_sessions = {}
chat_messages = {}


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
    team_name: Optional[str] = None
    is_anonymous_user: bool = False
    password_configured: bool = True


class AuthTypeMetadata(BaseModel):
    auth_type: str = "basic"
    auto_redirect: bool = False
    requires_verification: bool = False
    anonymous_user_enabled: bool = False
    password_min_length: int = 8
    has_users: bool = True
    oauth_enabled: bool = False


class Settings(BaseModel):
    auto_scroll: bool = True
    application_status: str = "active"
    gpu_enabled: bool = False
    maximum_chat_retention_days: Optional[str] = None
    notifications: list = []
    needs_reindexing: bool = False
    anonymous_user_enabled: bool = False
    invite_only_enabled: bool = False
    deep_research_enabled: bool = True
    temperature_override_enabled: bool = True
    query_history_type: str = "normal"


async def get_ollama_models() -> list[str]:
    """Fetch available Ollama models."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        print(f"Error fetching Ollama models: {e}")
    return [OLLAMA_MODEL]


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/ollama/models")
async def get_ollama_models_endpoint():
    """Get list of available Ollama models."""
    models = await get_ollama_models()
    return {"models": models, "default": OLLAMA_MODEL}


@app.get("/info")
async def get_info():
    """Return service metadata."""
    models = await get_ollama_models()
    return {
        "agents": [
            {"key": "chatbot", "name": "Chat Bot", "description": "Simple chatbot using Ollama"},
            {
                "key": "research-assistant",
                "name": "Research Assistant",
                "description": "Research with web search",
            },
        ],
        "models": models,
        "default_agent": "chatbot",
        "default_model": OLLAMA_MODEL,
    }


@app.get("/api/v1/auth/type")
async def get_auth_type_v1():
    return AuthTypeMetadata()


@app.get("/auth/type")
async def get_auth_type():
    return AuthTypeMetadata()


@app.get("/me")
async def get_current_user():
    return User()


@app.get("/api/me")
async def get_current_user_api():
    return User()


@app.post("/auth/login")
async def login(response: Response):
    response.set_cookie("session", "dev-session", httponly=True, samesite="lax")
    return {"success": True, "user_id": "dev-user-1"}


@app.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("session")
    return {"success": True}


@app.post("/auth/refresh")
async def refresh_auth():
    return {"success": True}


@app.get("/settings")
async def get_settings():
    return Settings()


@app.get("/api/settings")
async def get_settings_api():
    return Settings()


@app.get("/enterprise-settings")
async def get_enterprise_settings():
    return {"application_name": "Agentic AI", "use_custom_logo": False}


@app.get("/api/enterprise-settings")
async def get_enterprise_settings_api():
    return {"application_name": "Agentic AI", "use_custom_logo": False}


@app.get("/user/projects")
async def get_user_projects():
    return []


@app.get("/user/assistant/preferences")
async def get_user_assistant_preferences():
    return {}


@app.get("/user/files/recent")
async def get_recent_files():
    return []


@app.get("/api/llm/provider")
async def get_llm_provider():
    """Return LLM provider with Ollama models."""
    models = await get_ollama_models()
    default_model = models[0] if models else OLLAMA_MODEL

    return {
        "providers": [
            {
                "name": "Ollama",
                "provider": "ollama_chat",
                "provider_display_name": "Ollama",
                "model_configurations": [
                    {
                        "name": m,
                        "display_name": m,
                        "is_visible": True,
                        "max_input_tokens": 128000,
                        "supports_image_input": False,
                        "supports_reasoning": False,
                    }
                    for m in models
                ],
            }
        ],
        "default_text": {"provider_id": 1, "model_name": default_model},
        "default_vision": None,
    }


@app.get("/llm/provider")
async def get_llm_provider_no_prefix():
    return await get_llm_provider()


@app.get("/api/admin/llm/built-in/options")
async def get_llm_built_in_options():
    """Return built-in LLM options for admin."""
    models = await get_ollama_models()
    return {
        "providers": [
            {
                "name": "ollama",
                "display_name": "Ollama",
                "models": models,
                "default_model": OLLAMA_MODEL,
            }
        ]
    }


@app.get("/admin/llm/built-in/options")
async def get_llm_built_in_options_no_prefix():
    return await get_llm_built_in_options()


@app.post("/api/admin/llm/test/default")
async def test_llm_default():
    return {"success": True}


@app.post("/admin/llm/test/default")
async def test_llm_default_no_prefix():
    return {"success": True}


@app.get("/api/persona")
async def get_personas():
    """Return available agents/personas."""
    models = await get_ollama_models()
    default_model = models[0] if models else OLLAMA_MODEL

    return [
        {
            "id": 1,
            "name": "Chat Bot",
            "description": "Simple chatbot using Ollama",
            "tools": [],
            "starter_messages": [{"message": "Hello!", "name": "Greeting"}],
            "document_sets": [],
            "is_public": True,
            "is_visible": True,
            "display_priority": 100,
            "featured": True,
            "builtin_persona": True,
            "owner": None,
            "labels": [],
            "llm_model_version_override": default_model,
            "llm_model_provider_override": "ollama_chat",
        },
        {
            "id": 2,
            "name": "Research Assistant",
            "description": "Research assistant with web search capabilities",
            "tools": [],
            "starter_messages": [{"message": "Help me research topic", "name": "Research"}],
            "document_sets": [],
            "is_public": True,
            "is_visible": True,
            "display_priority": 90,
            "featured": True,
            "builtin_persona": True,
            "owner": None,
            "labels": [],
            "llm_model_version_override": default_model,
            "llm_model_provider_override": "ollama_chat",
        },
    ]


@app.get("/persona")
async def get_personas_no_prefix():
    return await get_personas()


@app.get("/api/persona/{persona_id}")
async def get_persona(persona_id: int):
    """Get a specific persona."""
    personas = await get_personas()
    for p in personas:
        if p["id"] == persona_id:
            return p
    return {"error": "Persona not found"}, 404


@app.get("/api/chat/get-user-chat-sessions")
async def get_chat_sessions():
    """Get user's chat sessions."""
    sessions = []
    for session_id, session_data in chat_sessions.items():
        sessions.append(
            {
                "id": session_id,
                "name": session_data.get("name", "New Chat"),
                "created_at": session_data.get("created_at", datetime.now().isoformat()),
                "last_updated": session_data.get("last_updated", datetime.now().isoformat()),
            }
        )
    return {"chat_sessions": sessions, "sessions": sessions}


@app.post("/api/chat/create-chat-session")
async def create_chat_session(request: Request):
    """Create a new chat session."""
    body = await request.json()
    persona_id = body.get("persona_id", 1)
    description = body.get("description", "New Chat")

    session_id = str(uuid.uuid4())
    chat_sessions[session_id] = {
        "id": session_id,
        "name": description,
        "persona_id": persona_id,
        "created_at": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
        "messages": [],
    }
    chat_messages[session_id] = []

    return {"chat_session_id": session_id, "name": description}


@app.get("/api/chat/get-chat-session/{session_id}")
async def get_chat_session(session_id: str):
    """Get a specific chat session with messages."""
    if session_id not in chat_sessions:
        return {"error": "Session not found"}, 404

    messages = chat_messages.get(session_id, [])
    return {"chat_session": chat_sessions[session_id], "messages": messages}


@app.post("/api/chat/send-chat-message")
async def send_chat_message(request: Request):
    """Stream chat messages using Ollama."""
    body = await request.json()
    message = body.get("message", "")
    chat_session_id = body.get("chat_session_id")
    parent_message_id = body.get("parent_message_id")

    model = body.get("model_override", {}).get("model_version", OLLAMA_MODEL)

    message_id = str(uuid.uuid4())

    if chat_session_id and chat_session_id not in chat_sessions:
        chat_sessions[chat_session_id] = {
            "id": chat_session_id,
            "name": "New Chat",
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "messages": [],
        }
        chat_messages[chat_session_id] = []

    user_message = {
        "id": message_id,
        "message": message,
        "role": "user",
        "created_at": datetime.now().isoformat(),
    }

    if chat_session_id:
        chat_messages.setdefault(chat_session_id, []).append(user_message)

    async def generate():
        full_response = ""

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {"role": m["role"], "content": m["message"]}
                            for m in chat_messages.get(chat_session_id, [])[-10:]
                        ]
                        + [{"role": "user", "content": message}],
                        "stream": True,
                    },
                ) as response:
                    assistant_message_id = str(uuid.uuid4())

                    async for line in response.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                if "message" in data:
                                    content = data["message"].get("content", "")
                                    if content:
                                        full_response += content
                                        msg_payload = {
                                            "type": "message",
                                            "message": {
                                                "id": assistant_message_id,
                                                "content": content,
                                                "role": "assistant",
                                            },
                                        }
                                        yield f"data: {json.dumps(msg_payload)}\n\n"
                                if data.get("done"):
                                    assistant_message = {
                                        "id": assistant_message_id,
                                        "message": full_response,
                                        "role": "assistant",
                                        "created_at": datetime.now().isoformat(),
                                    }
                                    if chat_session_id:
                                        chat_messages.setdefault(chat_session_id, []).append(
                                            assistant_message
                                        )
                                        chat_sessions[chat_session_id]["last_updated"] = (
                                            datetime.now().isoformat()
                                        )
                                    yield f"data: {json.dumps({'type': 'stop'})}\n\n"
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            yield f"data: {json.dumps({'type': 'error', 'error': error_msg})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.put("/api/chat/rename-chat-session")
async def rename_chat_session(request: Request):
    """Rename a chat session."""
    body = await request.json()
    session_id = body.get("chat_session_id")
    name = body.get("name", "Renamed Chat")

    if session_id in chat_sessions:
        chat_sessions[session_id]["name"] = name
        return {"success": True}
    return {"error": "Session not found"}, 404


@app.delete("/api/chat/delete-chat-session/{session_id}")
async def delete_chat_session(session_id: str):
    """Delete a chat session."""
    if session_id in chat_sessions:
        del chat_sessions[session_id]
        if session_id in chat_messages:
            del chat_messages[session_id]
        return {"success": True}
    return {"error": "Session not found"}, 404


@app.get("/api/notifications")
async def get_notifications():
    return []


@app.get("/notifications")
async def get_notifications_no_prefix():
    return []


@app.get("/api/input_prompt")
async def get_input_prompts():
    return []


@app.get("/input_prompt")
async def get_input_prompts_no_prefix():
    return []


@app.get("/api/manage/connector-status")
async def get_connector_status():
    return []


@app.get("/manage/connector-status")
async def get_connector_status_no_prefix():
    return []


@app.get("/api/federated/oauth-status")
async def get_federated_oauth_status():
    return {"enabled": False}


@app.get("/federated/oauth-status")
async def get_federated_oauth_status_no_prefix():
    return {"enabled": False}


@app.get("/api/federated")
async def get_federated():
    return []


@app.get("/federated")
async def get_federated_no_prefix():
    return []


@app.get("/api/query/valid-tags")
async def get_valid_tags():
    return []


@app.get("/query/valid-tags")
async def get_valid_tags_no_prefix():
    return []


@app.get("/api/manage/document-set")
async def get_document_sets():
    return []


@app.get("/manage/document-set")
async def get_document_sets_no_prefix():
    return []


@app.get("/api/admin/default-assistant")
async def get_default_assistant():
    return {"id": 1, "name": "Chat Bot"}


@app.get("/admin/default-assistant")
async def get_default_assistant_no_prefix():
    return await get_default_assistant()


@app.get("/api/chat/available-context-tokens")
async def get_available_context_tokens():
    return {"max_tokens": 128000, "selected_tokens": 128000}


@app.get("/api/user/projects")
async def get_user_projects_api():
    return []


@app.get("/api/user/assistant/preferences")
async def get_user_assistant_preferences_api():
    return {}


@app.get("/api/user/files/recent")
async def get_recent_files_api():
    return []


if __name__ == "__main__":
    print(f"Starting server with Ollama model: {OLLAMA_MODEL}")
    print(f"Ollama URL: {OLLAMA_BASE_URL}")
    uvicorn.run(app, host="0.0.0.0", port=8123)
