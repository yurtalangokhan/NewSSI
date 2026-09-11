"""
Chat session routes.

Endpoints: /api/chat/* (chat sessions and messages)
These endpoints delegate to ThreadController for CRUD and use message_generator for streaming.
"""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from i18n import t

from api.dependencies import (
    AuthenticatedUser,
    extract_auth_token_from_request,
    require_permission,
)
from api.routes.chat_route_helpers import (
    resolve_custom_persona_agent,
    resolve_effective_chat_user_id,
    resolve_project_id_from_chat_context,
    truncate_name,
)
from controller import ChatController, ThreadController, get_thread_controller, get_user_controller
from core.exceptions import FlowNotPublishedError, ForbiddenError
from core.logger import get_logger
from models.chat import StreamInput
from service.AgentStreamService import message_generator
from service.AuthService import get_auth_service, get_primary_user_id
from service.ChatAgentResolver import resolve_chat_agent
from service.ChatContextService import (
    build_effective_llm_override,
    resolve_project_instructions,
)
from service.ChatFileContextService import build_file_context
from service.ChatLlmOverrideService import apply_provider_llm_override
from service.ChatRequestService import (
    parse_chat_request,
    resolve_chat_identity,
    resolve_session_id,
)
from service.ChatThreadService import prepare_chat_thread

logger = get_logger(__name__)

# Re-export for backward compatibility (tests and callers that import from here)
_resolve_custom_persona_agent = resolve_custom_persona_agent
_resolve_effective_chat_user_id = resolve_effective_chat_user_id

router = APIRouter(tags=["chat"])


def _get_thread_controller() -> ThreadController:
    return get_thread_controller()


async def _get_user_chat_controller(request: Request, user: AuthenticatedUser) -> ChatController:
    identity = await get_auth_service().resolve_user_identity(
        token=extract_auth_token_from_request(request),
        user_id=user.user_id,
        user=user,
    )
    return ChatController(
        thread_controller=_get_thread_controller(),
        user_id=str(identity.get("primary_user_id") or user.user_id),
        owner_ids=identity.get("known_user_ids") or [user.user_id],
    )


def _coerce_project_id(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_project_id_from_chat_context(
    request_project_id: Any,
    thread: dict[str, Any] | None,
) -> int | None:
    resolved_project_id = _coerce_project_id(request_project_id)
    if resolved_project_id is not None or not isinstance(thread, dict):
        return resolved_project_id

    resolved_project_id = _coerce_project_id(thread.get("project_id"))
    if resolved_project_id is not None:
        return resolved_project_id

    metadata = thread.get("metadata") or {}
    if isinstance(metadata, dict):
        return _coerce_project_id(metadata.get("project_id"))

    return None


def _resolve_effective_chat_user_id(identity: dict[str, Any], user_id: str | None) -> str:
    effective_user_id = get_primary_user_id(identity, user_id)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail=t("auth.not_authenticated"))
    return effective_user_id


@router.get("/api/chat/sessions")
@router.get("/api/chat/get-user-chat-sessions")
async def get_chat_sessions(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:read"))],
    page_size: int = 100,
    before_activity: str | None = None,
    before_id: str | None = None,
):
    return await (await _get_user_chat_controller(request, user)).get_chat_sessions(
        page_size=page_size,
        before_activity=before_activity,
        before_id=before_id,
    )


@router.post("/api/chat/sessions")
@router.post("/api/chat/create-chat-session")
async def create_chat_session(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:send"))],
):
    body = await request.json()
    return await (await _get_user_chat_controller(request, user)).create_chat_session(
        persona_id=body.get("persona_id", 0),
        description=body.get("description"),
        project_id=body.get("project_id"),
    )


@router.get("/api/chat/sessions/{chat_session_id}")
@router.get("/api/chat/get-chat-session/{chat_session_id}")
async def get_chat_session(
    request: Request,
    chat_session_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:read"))],
):
    try:
        return await (await _get_user_chat_controller(request, user)).get_chat_session(
            chat_session_id
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.delete("/api/chat/sessions/{chat_session_id}")
@router.post("/api/chat/delete-chat-session/{chat_session_id}")
@router.delete("/api/chat/delete-chat-session/{chat_session_id}")
async def delete_chat_session(
    request: Request,
    chat_session_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:delete"))],
):
    result = await (await _get_user_chat_controller(request, user)).delete_chat_session(
        chat_session_id
    )
    if result.get("success") is False and result.get("error") == "Forbidden":
        raise HTTPException(status_code=403, detail=t("common.forbidden"))
    return result


@router.post("/api/chat/delete-all-chat-sessions")
@router.delete("/api/chat/delete-all-chat-sessions")
async def delete_all_chat_sessions(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:delete"))],
):
    return await (await _get_user_chat_controller(request, user)).delete_all_chat_sessions()


@router.put("/api/chat/rename-chat-session")
@router.patch("/api/chat/rename-chat-session")
async def rename_chat_session(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:send"))],
):
    body = await request.json()
    result = await (await _get_user_chat_controller(request, user)).rename_chat_session(
        session_id=body.get("chat_session_id"),
        name=body.get("name"),
    )
    if result.get("success") is False and result.get("error") == "Forbidden":
        raise HTTPException(status_code=403, detail=t("common.forbidden"))
    return result


@router.put("/api/chat/update-chat-session-model")
async def update_chat_session_model(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:send"))],
):
    body = await request.json()
    result = await (await _get_user_chat_controller(request, user)).update_chat_session_model(
        session_id=body.get("chat_session_id"),
        model=body.get("model"),
    )
    if result.get("success") is False and result.get("error") == "Forbidden":
        raise HTTPException(status_code=403, detail=t("common.forbidden"))
    return result


@router.put("/api/chat/update-chat-session-temperature")
async def update_chat_session_temperature(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:send"))],
):
    body = await request.json()
    result = await (await _get_user_chat_controller(request, user)).update_chat_session_temperature(
        session_id=body.get("chat_session_id"),
        temperature=body.get("temperature"),
    )
    if result.get("success") is False and result.get("error") == "Forbidden":
        raise HTTPException(status_code=403, detail=t("common.forbidden"))
    return result


@router.post("/api/chat/stop-chat-session/{chat_session_id}")
async def stop_chat_session(
    request: Request,
    chat_session_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:send"))],
):
    return await (await _get_user_chat_controller(request, user)).stop_chat_session(chat_session_id)


@router.put("/api/chat/set-message-as-latest")
async def set_message_as_latest(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:send"))],
):
    return await (await _get_user_chat_controller(request, user)).set_message_as_latest()


@router.get("/api/chat/available-context-tokens")
@router.get("/api/chat/available-context-tokens/{session_id}")
async def get_available_context_tokens(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:read"))],
    session_id: str = None,
):
    return await (await _get_user_chat_controller(request, user)).get_available_context_tokens(
        session_id
    )


@router.get("/api/user/projects/session/{session_id}/token-count")
@router.get("/user/projects/session/{session_id}/token-count")
async def get_session_token_count(
    request: Request,
    session_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:read"))],
):
    return await (await _get_user_chat_controller(request, user)).get_session_token_count(
        session_id
    )


@router.get("/api/user/projects/session/{session_id}/files")
@router.get("/user/projects/session/{session_id}/files")
async def get_session_files(
    request: Request,
    session_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:read"))],
):
    return await (await _get_user_chat_controller(request, user)).get_session_files(session_id)


@router.post("/api/chat/create-chat-message-feedback")
async def create_chat_message_feedback(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:send"))],
):
    return await (await _get_user_chat_controller(request, user)).create_chat_message_feedback()


@router.delete("/api/chat/remove-chat-message-feedback")
async def remove_chat_message_feedback(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:delete"))],
):
    return await (await _get_user_chat_controller(request, user)).remove_chat_message_feedback()


@router.post("/api/chat/messages")
@router.post("/api/chat/send-chat-message")
async def send_chat_message(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:send"))],
):
    """Send chat message with streaming - uses message_generator."""
    identity = await get_auth_service().resolve_user_identity(
        token=extract_auth_token_from_request(request),
        user_id=user.user_id,
        user=user,
    )
    try:
        effective_user_id = resolve_effective_chat_user_id(identity, user.user_id)
    except HTTPException:
        return StreamingResponse(
            iter([b'data: {"type": "error", "content": "Not authenticated"}\n\n']),
            media_type="text/event-stream",
            status_code=401,
        )
    user_controller = get_user_controller()
    chat_identity = await resolve_chat_identity(
        identity, user.user_id, effective_user_id, user_controller
    )
    known_user_ids = chat_identity.known_user_ids
    project_user_id = chat_identity.project_user_id

    try:
        body = await request.json()
    except Exception as e:
        logger.error("Failed to parse request body: %s", e)
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'content': 'Invalid JSON'})}\n\n"]),
            media_type="text/event-stream",
        )

    fields = parse_chat_request(body)
    message = fields.message
    persona_id = fields.persona_id
    llm_override = fields.llm_override
    additional_context = fields.additional_context

    # A client-supplied provider/model becomes a live LLM instance here, or
    # is stripped so a stale pair cannot reach the wrong backend.
    llm_override = await apply_provider_llm_override(llm_override, effective_user_id)

    session_id = resolve_session_id(fields.chat_session_id)

    session_name = truncate_name(message or "New Chat")
    thread_ctrl = _get_thread_controller()
    try:
        thread = await prepare_chat_thread(
            thread_ctrl,
            session_id=session_id,
            session_name=session_name,
            effective_user_id=effective_user_id,
            known_user_ids=known_user_ids,
            persona_id=persona_id,
            project_id=body.get("project_id"),
            llm_override=llm_override,
        )
    except ForbiddenError:
        return StreamingResponse(
            iter([b'data: {"type": "error", "content": "Forbidden"}\n\n']),
            media_type="text/event-stream",
            status_code=403,
        )

    try:
        await thread_ctrl.mark_message_activity(session_id)
    except Exception:
        logger.exception("Could not record accepted message activity for session %s", session_id)
    try:
        assistant_id, llm_override = await resolve_chat_agent(persona_id, llm_override)
    except FlowNotPublishedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "FLOW_NOT_PUBLISHED", "message": str(exc)},
        ) from exc

    # _resolve_custom_persona_agent only stamps _persona_id for custom
    # personas. Builtin/default personas need it too — retry relies on it to
    # report which agent produced a turn, per message, instead of falling
    # back to thread-level metadata.persona_id (last-write-wins, goes stale
    # the moment a later turn uses a different agent/model).
    if not isinstance(llm_override, dict):
        llm_override = dict(llm_override or {})
    llm_override.setdefault("_persona_id", persona_id if persona_id is not None else 0)

    thread_metadata = thread.get("metadata") if thread else None
    resolved_project_id = resolve_project_id_from_chat_context(
        body.get("project_id"),
        thread,
    )

    project_instructions = await resolve_project_instructions(
        user_id=project_user_id or effective_user_id,
        project_id=resolved_project_id,
        thread_metadata=thread_metadata,
    )
    llm_override = build_effective_llm_override(
        llm_override, additional_context, project_instructions
    )

    # Attachments: the request's own descriptors merged with the project's,
    # stored and turned into LLM content blocks. See ChatFileContextService.
    file_context = await build_file_context(
        body.get("file_descriptors") or [],
        user_controller=user_controller,
        known_user_ids=known_user_ids,
        effective_user_id=effective_user_id,
        session_id=session_id,
        resolved_project_id=resolved_project_id,
    )
    file_content_blocks = file_context.content_blocks
    files_metadata = file_context.files_metadata
    mail_attachments = file_context.mail_attachments

    stream_input = StreamInput(
        message=message or "",
        thread_id=session_id,
        agent_id=str(assistant_id),
        agent_config=llm_override or {},
        file_content_blocks=file_content_blocks,
        files_metadata=files_metadata,
        mail_attachments=mail_attachments,
        is_regenerate=bool(body.get("is_regenerate")),
        retry_target_message_id=(
            body.get("parent_message_id") if body.get("is_regenerate") else None
        ),
        is_edit=bool(body.get("edit_target_message_id")),
        edit_target_message_id=body.get("edit_target_message_id"),
        # Structured answer to a paused run (Human Input). Plain `message`
        # already resumes an interrupt; this carries a richer payload when the
        # client has one.
        resume_payload=body.get("resume_payload"),
    )

    async def generate_stream():
        full_response = ""
        try:
            async for chunk in message_generator(stream_input, assistant_id, effective_user_id):
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
            logger.error("Stream error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            full_response = f"Error: {str(e)}"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
