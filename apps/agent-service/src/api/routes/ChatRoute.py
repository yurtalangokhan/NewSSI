"""
Chat session routes.

Endpoints: /api/chat/* (chat sessions and messages)
These endpoints delegate to ThreadController for CRUD and use message_generator for streaming.
"""

import json
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from agents import DEFAULT_AGENT
from controller import ChatController, ThreadController, get_chat_controller, get_thread_controller
from schema.schema import StreamInput
from api.routes.AgentsRoute import message_generator

router = APIRouter(tags=["chat"])


def _get_thread_controller() -> ThreadController:
    return get_thread_controller()


def _get_chat_controller() -> ChatController:
    return get_chat_controller()


USER_ID = "dev-user"

PERSONA_ID_TO_AGENT: dict[int, str] = {
    0: "chatbot",
    1: "configurable-mcp-agent",
}


def _truncate_name(message: str, max_length: int = 50) -> str:
    name = message.strip()
    name = " ".join(name.split())
    if len(name) > max_length:
        name = name[:max_length].rsplit(" ", 1)[0] + "..."
    return name or "New Chat"


@router.get("/api/chat/get-user-chat-sessions")
async def get_chat_sessions():
    return await _get_chat_controller().get_chat_sessions()


@router.post("/api/chat/create-chat-session")
async def create_chat_session():
    return await _get_chat_controller().create_chat_session()


@router.get("/api/chat/get-chat-session/{chat_session_id}")
async def get_chat_session(chat_session_id: str):
    return await _get_chat_controller().get_chat_session(chat_session_id)


@router.post("/api/chat/delete-chat-session/{chat_session_id}")
@router.delete("/api/chat/delete-chat-session/{chat_session_id}")
async def delete_chat_session(chat_session_id: str):
    return await _get_chat_controller().delete_chat_session(chat_session_id)


@router.post("/api/chat/delete-all-chat-sessions")
@router.delete("/api/chat/delete-all-chat-sessions")
async def delete_all_chat_sessions():
    return await _get_chat_controller().delete_all_chat_sessions()


@router.put("/api/chat/rename-chat-session")
@router.patch("/api/chat/rename-chat-session")
async def rename_chat_session(request: Request):
    body = await request.json()
    return await _get_chat_controller().rename_chat_session(
        session_id=body.get("chat_session_id"),
        name=body.get("name"),
    )


@router.put("/api/chat/update-chat-session-model")
async def update_chat_session_model(request: Request):
    body = await request.json()
    return await _get_chat_controller().update_chat_session_model(
        session_id=body.get("chat_session_id"),
        model=body.get("model"),
    )


@router.put("/api/chat/update-chat-session-temperature")
async def update_chat_session_temperature(request: Request):
    body = await request.json()
    return await _get_chat_controller().update_chat_session_temperature(
        session_id=body.get("chat_session_id"),
        temperature=body.get("temperature"),
    )


@router.post("/api/chat/stop-chat-session/{chat_session_id}")
async def stop_chat_session(chat_session_id: str):
    return await _get_chat_controller().stop_chat_session(chat_session_id)


@router.put("/api/chat/set-message-as-latest")
async def set_message_as_latest():
    return await _get_chat_controller().set_message_as_latest()


@router.get("/api/chat/available-context-tokens")
@router.get("/api/chat/available-context-tokens/{session_id}")
async def get_available_context_tokens(session_id: str = None):
    return await _get_chat_controller().get_available_context_tokens(session_id)


@router.get("/user/projects/session/{session_id}/token-count")
async def get_session_token_count(session_id: str):
    return await _get_chat_controller().get_session_token_count(session_id)


@router.get("/user/projects/session/{session_id}/files")
async def get_session_files(session_id: str):
    return await _get_chat_controller().get_session_files(session_id)


@router.post("/api/chat/create-chat-message-feedback")
async def create_chat_message_feedback():
    return await _get_chat_controller().create_chat_message_feedback()


@router.delete("/api/chat/remove-chat-message-feedback")
async def remove_chat_message_feedback():
    return await _get_chat_controller().remove_chat_message_feedback()


@router.post("/api/chat/send-chat-message")
async def send_chat_message(request: Request):
    """Send chat message with streaming - uses message_generator."""
    import logging

    logger = logging.getLogger(__name__)

    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse request body: {e}")
        return StreamingResponse(
            iter([b"data: {'type': 'error', 'content': 'Invalid JSON'}\n\n"]),
            media_type="text/event-stream",
        )

    message = body.get("message") if body.get("message") is not None else ""
    chat_session_id = body.get("chat_session_id")
    persona_id = body.get("persona_id")
    llm_override = body.get("llm_override")

    session_id = chat_session_id
    if not session_id:
        session_id = str(uuid.uuid4())
        logger.info(f"Generated new session_id: {session_id}")

    try:
        uuid.UUID(session_id)
    except (ValueError, AttributeError):
        session_id = str(uuid.uuid4())
        logger.warning(f"Invalid session_id provided, generated new: {session_id}")

    session_name = _truncate_name(message or "New Chat")

    thread_ctrl = _get_thread_controller()
    thread = await thread_ctrl.get_thread(session_id)

    if not thread:
        thread = await thread_ctrl.create_thread(
            thread_id=session_id,
            metadata={
                "user_id": USER_ID,
                "name": session_name,
                "persona_id": persona_id,
            }
        )
    else:
        metadata = thread.get("metadata", {}) or {}
        needs_update = False
        if metadata.get("name") in (None, "", "New Chat"):
            metadata["name"] = session_name
            needs_update = True
        if persona_id is not None and metadata.get("persona_id") != persona_id:
            metadata["persona_id"] = persona_id
            needs_update = True
        if llm_override:
            if llm_override.get("model"):
                metadata["current_alternate_model"] = llm_override["model"]
                needs_update = True
            if llm_override.get("temperature") is not None:
                metadata["current_temperature_override"] = llm_override["temperature"]
                needs_update = True
        if needs_update:
            await thread_ctrl.update_thread(session_id, metadata)

    assistant_id = PERSONA_ID_TO_AGENT.get(persona_id, DEFAULT_AGENT) if persona_id else DEFAULT_AGENT

    if persona_id is not None:
        from service.PersonaRepository import PersonaDB
        try:
            custom_persona = await PersonaDB.get(persona_id)
        except Exception:
            custom_persona = None

        if custom_persona and not custom_persona.get("is_builtin"):
            assistant_id = custom_persona.get("base_agent") or DEFAULT_AGENT
            if custom_persona.get("system_prompt"):
                llm_override = llm_override or {}
                llm_override["system_prompt"] = custom_persona["system_prompt"]
            if custom_persona.get("mcp_tools"):
                llm_override = llm_override or {}
                llm_override["mcp_tools"] = custom_persona["mcp_tools"]
            if custom_persona.get("rag_config"):
                llm_override = llm_override or {}
                llm_override["rag_config"] = custom_persona["rag_config"]

    stream_input = StreamInput(
        message=message or "",
        thread_id=session_id,
        agent_config=llm_override or {},
    )

    async def generate_stream():
        full_response = ""
        try:
            async for chunk in message_generator(stream_input, assistant_id, USER_ID):
                yield chunk

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
