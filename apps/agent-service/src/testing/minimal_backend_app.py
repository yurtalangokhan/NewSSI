"""
Minimal FastAPI server that provides the endpoints needed by the Onyx frontend.
This is a simplified backend for development purposes.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.api_versioning import API_PREFIX
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
@app.get(f"{API_PREFIX}/health")
async def health_check():
    return {"status": "ok"}


@app.get(f"{API_PREFIX}/me")
async def get_current_user():
    return User()


# Settings endpoints
@app.get(f"{API_PREFIX}/settings")
async def get_settings():
    return Settings()


@app.get(f"{API_PREFIX}/enterprise-settings")
async def get_enterprise_settings():
    return {"application_name": "Agentic AI", "use_custom_logo": False}


# Chat endpoints
@app.get(f"{API_PREFIX}/chat/get-user-chat-sessions")
async def get_chat_sessions():
    return {"chat_sessions": [], "sessions": []}


@app.post(f"{API_PREFIX}/chat/create-chat-session")
async def create_chat_session():
    return {"chat_session_id": "new-session-1", "name": "New Chat"}


# Persona endpoints
@app.get(f"{API_PREFIX}/persona")
async def get_personas():
    return []


# User endpoints
@app.get(f"{API_PREFIX}/user/projects")
async def get_user_projects():
    return []


@app.get(f"{API_PREFIX}/notifications")
async def get_notifications():
    return []


@app.get(f"{API_PREFIX}/input_prompt")
async def get_input_prompts():
    return []


@app.get(f"{API_PREFIX}/input_promt")
async def get_input_prompts_typo_alias():
    return await get_input_prompts()


@app.get(f"{API_PREFIX}/manage/connector-status")
async def get_connector_status():
    return []


@app.get(f"{API_PREFIX}/federated/oauth-status")
async def get_federated_oauth_status():
    return {"enabled": False}


@app.get(f"{API_PREFIX}/federated")
async def get_federated():
    return []


@app.get(f"{API_PREFIX}/query/valid-tags")
async def get_valid_tags():
    return []


@app.get(f"{API_PREFIX}/manage/document-set")
async def get_document_sets():
    return []


@app.get(f"{API_PREFIX}/llm/provider")
async def get_llm_provider():
    return {"providers": [], "selected_provider": None}


@app.get(f"{API_PREFIX}/user/assistant/preferences")
async def get_user_assistant_preferences():
    return {}


@app.get(f"{API_PREFIX}/admin/llm/built-in/options")
async def get_llm_built_in_options():
    return {}


@app.post(f"{API_PREFIX}/admin/llm/test/default")
async def test_llm_default():
    return {"success": True}


@app.get(f"{API_PREFIX}/user/files/recent")
async def get_recent_files():
    return []


@app.get(f"{API_PREFIX}/admin/default-assistant")
async def get_default_assistant():
    return None


@app.get(f"{API_PREFIX}/chat/available-context-tokens")
async def get_available_context_tokens():
    return {"max_tokens": 120000, "selected_tokens": 120000}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8123)
