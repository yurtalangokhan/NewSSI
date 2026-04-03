"""
Minimal FastAPI server that provides the endpoints needed by the Onyx frontend.
This is a simplified backend for development purposes.
"""


from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Agentic AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Models
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
    anonymousUserEnabled: bool = True
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
    anonymous_user_enabled: bool = True
    invite_only_enabled: bool = False
    deep_research_enabled: bool = True
    temperature_override_enabled: bool = True
    query_history_type: str = "normal"


# Health
@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/health")
async def api_health_check():
    return {"status": "ok"}


# Auth endpoints
@app.get("/auth/type")
async def get_auth_type():
    return AuthTypeMetadata()


@app.get("/me")
async def get_current_user():
    return User()


@app.get("/api/me")
async def get_api_me():
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


@app.post("/api/auth/refresh")
async def api_refresh_auth():
    return {"success": True}


# Settings endpoints
@app.get("/settings")
async def get_settings():
    return Settings()


@app.get("/enterprise-settings")
async def get_enterprise_settings():
    return {"application_name": "Agentic AI", "use_custom_logo": False}


# Chat endpoints
@app.get("/api/chat/get-user-chat-sessions")
async def get_chat_sessions():
    return {"chat_sessions": [], "sessions": []}


@app.post("/api/chat/create-chat-session")
async def create_chat_session():
    return {"chat_session_id": "new-session-1", "name": "New Chat"}


# Persona endpoints
@app.get("/api/persona")
async def get_personas():
    return []


# User endpoints
@app.get("/api/user/projects")
async def get_user_projects():
    return []


@app.get("/api/notifications")
async def get_notifications():
    return []


@app.get("/api/input_prompt")
async def get_input_prompts():
    return []


@app.get("/api/manage/connector-status")
async def get_connector_status():
    return []


@app.get("/api/federated/oauth-status")
async def get_federated_oauth_status():
    return {"enabled": False}


@app.get("/api/federated")
async def get_federated():
    return []


@app.get("/api/query/valid-tags")
async def get_valid_tags():
    return []


@app.get("/api/manage/document-set")
async def get_document_sets():
    return []


@app.get("/api/llm/provider")
async def get_llm_provider():
    return {"providers": [], "selected_provider": None}


@app.get("/api/user/assistant/preferences")
async def get_user_assistant_preferences():
    return {}


@app.get("/api/admin/llm/built-in/options")
async def get_llm_built_in_options():
    return {}


@app.post("/api/admin/llm/test/default")
async def test_llm_default():
    return {"success": True}


@app.get("/api/user/files/recent")
async def get_recent_files():
    return []


@app.get("/api/admin/default-assistant")
async def get_default_assistant():
    return None


@app.get("/api/chat/available-context-tokens")
async def get_available_context_tokens():
    return {"max_tokens": 120000, "selected_tokens": 120000}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8123)
