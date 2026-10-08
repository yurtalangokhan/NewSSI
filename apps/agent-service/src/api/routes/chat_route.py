"""
Chat session routes.

Endpoints: /api/chat/* (chat sessions and messages)
These endpoints delegate to ChatManagementService for CRUD and use message_generator for streaming.
"""

import json
from typing import Annotated, Any

from error_contract import ApplicationError, BadRequestError, NotFoundError, UnauthorizedError, ValidationFailedError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from api.dependencies import AuthenticatedUser, extract_auth_token_from_request, require_permission
from api.helpers.chat_route_helpers import (
    coerce_project_id,
    parse_resume_position,
    resolve_effective_chat_user_id,
    resolve_project_id_from_chat_context,
    truncate_name,
)
from core.exceptions import FlowNotPublishedError, ForbiddenError
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from core.observability.logger import get_logger
from schemas.agent_config_policy import CLIENT_ALLOWED_LLM_OVERRIDE_KEYS, sanitize_client_agent_config
from schemas.chat import (
    AvailableContextTokensResponse,
    ChatSessionDetailResponse,
    ChatSessionItemResponse,
    ChatSessionListResponse,
    CreateChatSessionPayload,
    DeleteAllSessionsResponse,
    RenameChatSessionPayload,
    SessionFileItemResponse,
    SessionTokenCountResponse,
    StreamInput,
    UpdateChatSessionModelPayload,
    UpdateChatSessionTemperaturePayload,
)
from schemas.chat_runs import ActiveRunDTO, ActiveRunResponse
from schemas.common import SuccessResponse
from service.auth.auth_service import get_auth_service
from service.chat import ChatManagementService
from service.chat.chat_agent_resolver import resolve_chat_agent
from service.chat.chat_context_service import (
    build_effective_llm_override,
    build_server_config,
    resolve_project_instructions,
)
from service.chat.chat_file_context_service import build_file_context
from service.chat.chat_llm_override_service import apply_provider_llm_override
from service.chat.chat_request_service import parse_chat_request, resolve_chat_identity, resolve_session_id
from service.chat.chat_thread_service import prepare_chat_thread
from service.chat_runs.domain import ChatRunSpec
from service.chat_runs.provider import get_chat_run_service
from service.orchestration.agent_stream_service import message_generator
from service.stream.error_events import guard_stream
from service.threads import ThreadAccessService, get_thread_access_service
from service.users import get_user_service

logger = get_logger(__name__)
_resolve_effective_chat_user_id = resolve_effective_chat_user_id
router = APIRouter(tags=["chat"])

SSE_HEADERS = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}


def _get_thread_service() -> ThreadAccessService:
    return get_thread_access_service()


async def _get_user_chat_service(request: Request, user: AuthenticatedUser) -> ChatManagementService:
    identity = await get_auth_service().resolve_user_identity(
        token=extract_auth_token_from_request(request), user_id=user.user_id, user=user
    )
    return ChatManagementService(
        thread_service=_get_thread_service(),
        user_id=str(identity.get("primary_user_id") or user.user_id),
        owner_ids=identity.get("known_user_ids") or [user.user_id],
    )


_coerce_project_id = coerce_project_id
_resolve_project_id_from_chat_context = resolve_project_id_from_chat_context
_resolve_effective_chat_user_id = resolve_effective_chat_user_id


@router.get("/api/chat/sessions", response_model=ResponseModel[ChatSessionListResponse])
async def get_chat_sessions(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:read"))],
    page_size: int = 100,
    before_activity: str | None = None,
    before_id: str | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    agents_only: bool = False,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await (await _get_user_chat_service(request, user)).get_chat_sessions(
                page_size=page_size,
                before_activity=before_activity,
                before_id=before_id,
                query=q,
                agents_only=agents_only,
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/chat/sessions", response_model=ResponseModel[ChatSessionItemResponse])
async def create_chat_session(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:send"))],
    body: CreateChatSessionPayload | None = None,
) -> ResponseModel[Any]:
    try:
        payload = body or CreateChatSessionPayload()
        return ResponseModel(
            data=await (await _get_user_chat_service(request, user)).create_chat_session(
                persona_id=payload.persona_id, description=payload.description, project_id=payload.project_id
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/chat/sessions/{chat_session_id}", response_model=ResponseModel[ChatSessionDetailResponse])
async def get_chat_session(
    response: Response,
    request: Request,
    chat_session_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=await (await _get_user_chat_service(request, user)).get_chat_session(chat_session_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/chat/sessions/{session_id}/seen", response_model=ResponseModel[SuccessResponse])
async def mark_chat_session_seen(
    response: Response,
    request: Request,
    session_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:read"))],
) -> ResponseModel[Any]:
    try:
        await (await _get_user_chat_service(request, user)).mark_session_seen(session_id)
        return ResponseModel(data=SuccessResponse())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/api/chat/sessions/{chat_session_id}", response_model=ResponseModel[SuccessResponse])
async def delete_chat_session(
    response: Response,
    request: Request,
    chat_session_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:delete"))],
) -> ResponseModel[Any]:
    try:
        result = await (await _get_user_chat_service(request, user)).delete_chat_session(chat_session_id)
        return ResponseModel(data=result)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/api/chat/delete-all-chat-sessions", response_model=ResponseModel[DeleteAllSessionsResponse])
async def delete_all_chat_sessions(
    response: Response, request: Request, user: Annotated[AuthenticatedUser, Depends(require_permission("chat:delete"))]
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=await (await _get_user_chat_service(request, user)).delete_all_chat_sessions())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.put("/api/chat/rename-chat-session", response_model=ResponseModel[SuccessResponse])
async def rename_chat_session(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:send"))],
    body: RenameChatSessionPayload | None = None,
) -> ResponseModel[Any]:
    try:
        payload = body or RenameChatSessionPayload()
        result = await (await _get_user_chat_service(request, user)).rename_chat_session(
            session_id=payload.chat_session_id, name=payload.name
        )
        return ResponseModel(data=result)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.put("/api/chat/update-chat-session-model", response_model=ResponseModel[SuccessResponse])
async def update_chat_session_model(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:send"))],
    body: UpdateChatSessionModelPayload | None = None,
) -> ResponseModel[Any]:
    try:
        payload = body or UpdateChatSessionModelPayload()
        result = await (await _get_user_chat_service(request, user)).update_chat_session_model(
            session_id=payload.chat_session_id, model=payload.model
        )
        return ResponseModel(data=result)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.put("/api/chat/update-chat-session-temperature", response_model=ResponseModel[SuccessResponse])
async def update_chat_session_temperature(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:send"))],
    body: UpdateChatSessionTemperaturePayload | None = None,
) -> ResponseModel[Any]:
    try:
        payload = body or UpdateChatSessionTemperaturePayload()
        result = await (await _get_user_chat_service(request, user)).update_chat_session_temperature(
            session_id=payload.chat_session_id, temperature=payload.temperature
        )
        return ResponseModel(data=result)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/chat/stop-chat-session/{chat_session_id}", response_model=ResponseModel[SuccessResponse])
async def stop_chat_session(
    response: Response,
    request: Request,
    chat_session_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:send"))],
    # The Idempotency-Key of the send being stopped: reaches a send whose run
    # is not registered yet (the Stop button is live while the POST is prepared).
    client_request_id: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await (await _get_user_chat_service(request, user)).stop_chat_session(
                chat_session_id, client_request_id=client_request_id
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/chat/sessions/{session_id}/active-run")
async def get_active_chat_run(
    session_id: str,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:read"))],
) -> ActiveRunResponse:
    chats = await _get_user_chat_service(request, user)
    if not await chats.can_access_session(session_id):
        raise NotFoundError(message_key="chat.session_not_found")
    run = await get_chat_run_service().get_active_run(session_id, owner_ids=chats.owner_ids)
    return ActiveRunResponse(active_run=ActiveRunDTO.from_run(run) if run else None)


@router.get(
    "/api/chat/runs/{run_id}/events",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
            "description": "Replayable stream of a chat run's events (SSE)",
        }
    },
)
async def stream_chat_run_events(
    run_id: str,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:read"))],
    after: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    try:
        after_seq = parse_resume_position(last_event_id, after)
    except ValueError as exc:
        raise ValidationFailedError(details={"field": "Last-Event-ID"}) from exc
    chats = await _get_user_chat_service(request, user)
    events = await get_chat_run_service().open_events(run_id, after_seq=after_seq, owner_ids=chats.owner_ids)
    return StreamingResponse(events, media_type="text/event-stream", headers=SSE_HEADERS)


@router.put("/api/chat/set-message-as-latest", response_model=ResponseModel[SuccessResponse])
async def set_message_as_latest(
    response: Response, request: Request, user: Annotated[AuthenticatedUser, Depends(require_permission("chat:send"))]
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=await (await _get_user_chat_service(request, user)).set_message_as_latest())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get(
    "/api/chat/available-context-tokens/{session_id}", response_model=ResponseModel[AvailableContextTokensResponse]
)
async def get_available_context_tokens(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:read"))],
    session_id: str | None = None,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await (await _get_user_chat_service(request, user)).get_available_context_tokens(session_id)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/user/projects/session/{session_id}/token-count", response_model=ResponseModel[SessionTokenCountResponse])
async def get_session_token_count(
    response: Response,
    request: Request,
    session_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await (await _get_user_chat_service(request, user)).get_session_token_count(session_id)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/user/projects/session/{session_id}/files", response_model=ResponseModel[list[SessionFileItemResponse]])
async def get_session_files(
    response: Response,
    request: Request,
    session_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=await (await _get_user_chat_service(request, user)).get_session_files(session_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/chat/create-chat-message-feedback", response_model=ResponseModel[SuccessResponse])
async def create_chat_message_feedback(
    response: Response, request: Request, user: Annotated[AuthenticatedUser, Depends(require_permission("chat:send"))]
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=await (await _get_user_chat_service(request, user)).create_chat_message_feedback())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/api/chat/remove-chat-message-feedback", response_model=ResponseModel[SuccessResponse])
async def remove_chat_message_feedback(
    response: Response, request: Request, user: Annotated[AuthenticatedUser, Depends(require_permission("chat:delete"))]
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=await (await _get_user_chat_service(request, user)).remove_chat_message_feedback())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post(
    "/api/chat/messages",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
            "description": "Stream of chat message events (SSE)",
        }
    },
)
async def send_chat_message(
    request: Request, user: Annotated[AuthenticatedUser, Depends(require_permission("chat:send"))]
):
    """Send chat message with streaming - uses message_generator."""
    identity = await get_auth_service().resolve_user_identity(
        token=extract_auth_token_from_request(request), user_id=user.user_id, user=user
    )
    try:
        effective_user_id = resolve_effective_chat_user_id(identity, user.user_id)
    except HTTPException as exc:
        raise UnauthorizedError() from exc
    user_service = get_user_service()
    chat_identity = await resolve_chat_identity(identity, user.user_id, effective_user_id, user_service)
    known_user_ids = chat_identity.known_user_ids
    project_user_id = chat_identity.project_user_id
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BadRequestError() from exc
    if not isinstance(body, dict):
        raise BadRequestError()
    fields = parse_chat_request(body)
    message = fields.message
    from service.personas import get_persona_service

    persona_id = await get_persona_service().authorize_chat_persona(fields.persona_id, user)
    llm_override = sanitize_client_agent_config(
        fields.llm_override, source="llm_override", allowed_keys=CLIENT_ALLOWED_LLM_OVERRIDE_KEYS
    )
    additional_context = fields.additional_context
    llm_override = await apply_provider_llm_override(llm_override, effective_user_id)
    session_id = resolve_session_id(fields.chat_session_id)

    chat_runs = get_chat_run_service()
    await chat_runs.ensure_idle(session_id, owner_ids={effective_user_id, *known_user_ids})

    session_name = truncate_name(message or "New Chat")
    thread_service = _get_thread_service()
    try:
        thread = await prepare_chat_thread(
            thread_service,
            session_id=session_id,
            session_name=session_name,
            effective_user_id=effective_user_id,
            known_user_ids=known_user_ids,
            persona_id=persona_id,
            project_id=body.get("project_id"),
            llm_override=llm_override,
        )
    except ForbiddenError:
        raise
    try:
        await thread_service.mark_message_activity(session_id)
    except Exception:
        logger.exception("Could not record accepted message activity for session %s", session_id)
    try:
        assistant_id, llm_override = await resolve_chat_agent(persona_id, llm_override)
    except FlowNotPublishedError:
        raise
    if not isinstance(llm_override, dict):
        llm_override = dict(llm_override or {})
    llm_override.setdefault("_persona_id", persona_id if persona_id is not None else 0)
    resolved_override = llm_override
    thread_metadata = thread.get("metadata") if thread else None
    resolved_project_id = resolve_project_id_from_chat_context(body.get("project_id"), thread)
    project_instructions = await resolve_project_instructions(
        user_id=project_user_id or effective_user_id, project_id=resolved_project_id, thread_metadata=thread_metadata
    )
    llm_override = build_effective_llm_override(llm_override, additional_context, project_instructions)
    file_context = await build_file_context(
        body.get("file_descriptors") or [],
        user_service=user_service,
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
        retry_target_message_id=body.get("parent_message_id") if body.get("is_regenerate") else None,
        is_edit=bool(body.get("edit_target_message_id")),
        edit_target_message_id=body.get("edit_target_message_id"),
        resume_payload=body.get("resume_payload"),
        document_context=fields.document_context,
    )
    stream_input.attach_server_config(build_server_config(resolved_override, llm_override))

    spec = ChatRunSpec(
        thread_id=session_id,
        owner_user_id=str(effective_user_id),
        input_preview=message or "",
        client_request_id=request.headers.get("Idempotency-Key"),
    )
    # The run lives in the supervisor: this response is only a subscriber, so a
    # disconnect ends the subscription, never the run.
    run, events = await chat_runs.start_and_subscribe(
        spec, lambda: guard_stream(message_generator(stream_input, assistant_id, effective_user_id))
    )
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={**SSE_HEADERS, "X-Chat-Run-Id": run.run_id},
    )
