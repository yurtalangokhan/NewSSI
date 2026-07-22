"""
Minimal FastAPI server that provides the endpoints needed by the Onyx frontend.
This is a simplified backend for development purposes.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models.minimal_backend import Settings, User

app = FastAPI(title="Agentic AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health
@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/health")
async def api_health_check():
    return {"status": "ok"}


@app.get("/me")
async def get_current_user():
    return User()


@app.get("/api/me")
async def get_api_me():
    return User()


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


@app.get("/api/input_promt")
async def get_input_prompts_typo_alias():
    return await get_input_prompts()


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
