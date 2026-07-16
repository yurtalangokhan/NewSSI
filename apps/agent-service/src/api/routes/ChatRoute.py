"""
Chat session routes.

Endpoints: /api/chat/* (chat sessions and messages)
These endpoints delegate to ThreadController for CRUD and use message_generator for streaming.
"""

import json
import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from agents import DEFAULT_AGENT
from api.dependencies import AuthenticatedUser, require_permission
from api.routes.AgentsRoute import message_generator
from controller import ChatController, ThreadController, get_thread_controller, get_user_controller
from domain.providers.repository import ProviderRepository
from domain.providers.service import ProviderService
from models.chat import StreamInput
from service.AuthService import get_auth_service, get_primary_user_id
from service.ChatContextService import (
    build_effective_llm_override,
    resolve_project_instructions,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def _get_thread_controller() -> ThreadController:
    return get_thread_controller()


async def _get_user_chat_controller(request: Request, user: AuthenticatedUser) -> ChatController:
    identity = await get_auth_service().resolve_user_identity(
        request=request,
        user_id=user.user_id,
        user=user,
    )
    return ChatController(
        thread_controller=_get_thread_controller(),
        user_id=str(identity.get("primary_user_id") or user.user_id),
        owner_ids=identity.get("known_user_ids") or [user.user_id],
    )


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


def _coerce_project_id(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_effective_chat_user_id(identity: dict[str, Any], user_id: str | None) -> str:
    effective_user_id = get_primary_user_id(identity, user_id)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return effective_user_id


async def _resolve_provider_for_user(
    user_id: str, provider_id: str, repo: ProviderRepository
) -> dict[str, Any] | None:
    provider_svc = ProviderService(repo)
    all_providers = await provider_svc.list_all(user_id)
    all_entries = [
        *all_providers.get("builtin", []),
        *all_providers.get("url_providers", []),
        *all_providers.get("user_providers", []),
    ]
    for provider in all_entries:
        if str(provider.get("id")) == str(provider_id):
            return provider
    return None


async def _resolve_model_supports_reasoning(
    *,
    user_id: str,
    provider_id: str,
    provider: dict[str, Any],
    model_name: str,
    repo: ProviderRepository,
) -> bool | None:
    """Resolve model reasoning capability from provider model metadata.

    Priority:
    1) provider.config.model_configurations (persisted sync metadata)
    2) live provider model fetch fallback (for built-ins / unsynced providers)
    """
    config = provider.get("config") or {}
    model_configurations = config.get("model_configurations") or []
    if isinstance(model_configurations, list):
        for model in model_configurations:
            if model.get("name") == model_name:
                return bool(model.get("supports_reasoning", False))

    try:
        provider_svc = ProviderService(repo)
        live_models = await provider_svc.get_models_for_provider(provider_id, user_id)
        for model in live_models:
            if model.get("name") == model_name:
                return bool(model.get("supports_reasoning", False))
    except Exception as exc:
        logger.debug(
            "Could not resolve model capability for provider_id=%s model=%s: %s",
            provider_id,
            model_name,
            exc,
        )

    return None


@router.get("/api/chat/get-user-chat-sessions")
async def get_chat_sessions(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:read"))],
):
    return await (await _get_user_chat_controller(request, user)).get_chat_sessions()


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


@router.get("/api/chat/get-chat-session/{chat_session_id}")
async def get_chat_session(
    request: Request,
    chat_session_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:read"))],
):
    try:
        return await (await _get_user_chat_controller(request, user)).get_chat_session(chat_session_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/api/chat/delete-chat-session/{chat_session_id}")
@router.delete("/api/chat/delete-chat-session/{chat_session_id}")
async def delete_chat_session(
    request: Request,
    chat_session_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:delete"))],
):
    result = await (await _get_user_chat_controller(request, user)).delete_chat_session(chat_session_id)
    if result.get("success") is False and result.get("error") == "Forbidden":
        raise HTTPException(status_code=403, detail="Forbidden")
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
        raise HTTPException(status_code=403, detail="Forbidden")
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
        raise HTTPException(status_code=403, detail="Forbidden")
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
        raise HTTPException(status_code=403, detail="Forbidden")
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
    return await (await _get_user_chat_controller(request, user)).get_available_context_tokens(session_id)


@router.get("/api/user/projects/session/{session_id}/token-count")
@router.get("/user/projects/session/{session_id}/token-count")
async def get_session_token_count(
    request: Request,
    session_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:read"))],
):
    return await (await _get_user_chat_controller(request, user)).get_session_token_count(session_id)


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


@router.post("/api/chat/send-chat-message")
async def send_chat_message(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("chat:send"))],
):
    """Send chat message with streaming - uses message_generator."""
    identity = await get_auth_service().resolve_user_identity(
        request=request,
        user_id=user.user_id,
        user=user,
    )
    try:
        effective_user_id = _resolve_effective_chat_user_id(identity, user.user_id)
    except HTTPException:
        return StreamingResponse(
            iter([b'data: {"type": "error", "content": "Not authenticated"}\n\n']),
            media_type="text/event-stream",
            status_code=401,
        )
    known_user_ids = {
        str(candidate)
        for candidate in (identity.get("known_user_ids") or [effective_user_id])
        if candidate
    }
    known_user_ids.add(effective_user_id)
    user_controller = get_user_controller()
    project_user_id = await user_controller.resolve_projects_user_id(
        str(identity.get("keycloak_id") or effective_user_id)
    )
    if project_user_id:
        known_user_ids.add(str(project_user_id))

    try:
        body = await request.json()
    except Exception as e:
        logger.error("Failed to parse request body: %s", e)
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'content': 'Invalid JSON'})}\n\n"]),
            media_type="text/event-stream",
        )

    message = body.get("message") if body.get("message") is not None else ""
    chat_session_id = body.get("chat_session_id")
    persona_id = body.get("persona_id")
    llm_override = body.get("llm_override")
    additional_context = body.get("additional_context")
    if isinstance(additional_context, str):
        additional_context = additional_context.strip() or None
    else:
        additional_context = None

    if llm_override and llm_override.get("provider_id") and llm_override.get("provider_type"):
        model_name = llm_override.get("model") or llm_override.get("model_version")
        provider_resolution_failed = False
        if model_name:
            try:
                from core.llm_factory import get_llm_for_provider

                provider_id = str(llm_override["provider_id"])
                logger.debug("Resolving provider: provider_id=%s, provider_type=%s, model=%s", provider_id, llm_override["provider_type"], model_name)
                repo = ProviderRepository()
                provider = await _resolve_provider_for_user(effective_user_id, provider_id, repo)

                api_key = None
                base_url = None
                api_version = None
                request_overrides = None

                if provider:
                    logger.debug("Found provider in registry: %s", provider)
                    # Only fetch API key for DB-stored (non-builtin) providers
                    if not provider.get("is_builtin"):
                        api_key = await repo.get_decrypted_api_key(provider_id, effective_user_id)
                    base_url = provider.get("base_url") or (provider.get("user_config") or {}).get("api_base")
                    api_version = (provider.get("user_config") or {}).get("api_version")
                    request_overrides = ((provider.get("config") or {}).get("custom_config") or {}).get(
                        "request_overrides"
                    )
                    provider_type = provider.get("provider_type") or llm_override["provider_type"]
                    supports_reasoning = await _resolve_model_supports_reasoning(
                        user_id=effective_user_id,
                        provider_id=provider_id,
                        provider=provider,
                        model_name=model_name,
                        repo=repo,
                    )
                else:
                    logger.warning("Provider %s not found for user %s", provider_id, effective_user_id)
                    provider_resolution_failed = True
                    provider_type = llm_override["provider_type"]
                    supports_reasoning = None

                if not provider_resolution_failed:
                    llm_override["llm_instance"] = await get_llm_for_provider(
                        model_name,
                        provider_type,
                        api_key=api_key,
                        base_url=base_url,
                        api_version=api_version,
                        supports_reasoning=supports_reasoning,
                        request_overrides=request_overrides,
                    )
                    logger.debug("Successfully created LLM instance for model %s", model_name)
            except Exception as exc:
                provider_resolution_failed = True
                logger.exception("Provider-aware LLM resolution failed: %s", exc)

        if provider_resolution_failed:
            # Prevent stale/incompatible model fallback (e.g. Gemini model routed to Ollama).
            for key in ("model", "model_version", "provider_id", "provider_type", "llm_instance"):
                llm_override.pop(key, None)

    session_id = chat_session_id
    if not session_id:
        session_id = str(uuid.uuid4())
        logger.info("Generated new session_id: %s", session_id)

    try:
        uuid.UUID(session_id)
    except (ValueError, AttributeError):
        session_id = str(uuid.uuid4())
        logger.warning("Invalid session_id provided, generated new: %s", session_id)

    session_name = _truncate_name(message or "New Chat")

    thread_ctrl = _get_thread_controller()
    thread = await thread_ctrl.get_thread(session_id)

    if not thread:
        thread = await thread_ctrl.create_thread(
            thread_id=session_id,
            metadata={
                "user_id": effective_user_id,
                "name": session_name,
                "persona_id": persona_id,
                "project_id": body.get("project_id"),
            }
        )
    else:
        metadata = thread.get("metadata", {}) or {}
        owner_id = metadata.get("user_id")
        if owner_id and str(owner_id) not in known_user_ids:
            return StreamingResponse(
                iter([b'data: {"type": "error", "content": "Forbidden"}\n\n']),
                media_type="text/event-stream",
                status_code=403,
            )
        if not owner_id:
            metadata["user_id"] = effective_user_id
        elif str(owner_id) != effective_user_id:
            legacy_owner_ids = metadata.get("legacy_user_ids") or []
            if not isinstance(legacy_owner_ids, list):
                legacy_owner_ids = []
            if str(owner_id) not in legacy_owner_ids:
                legacy_owner_ids.append(str(owner_id))
            metadata["legacy_user_ids"] = legacy_owner_ids
            metadata["user_id"] = effective_user_id

        needs_update = metadata.get("user_id") == effective_user_id and str(owner_id) != effective_user_id
        if metadata.get("name") in (None, "", "New Chat"):
            metadata["name"] = session_name
            needs_update = True
        if persona_id is not None and metadata.get("persona_id") != persona_id:
            metadata["persona_id"] = persona_id
            needs_update = True
        if body.get("project_id") is not None and metadata.get("project_id") != body.get("project_id"):
            metadata["project_id"] = body.get("project_id")
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

    assistant_id = DEFAULT_AGENT

    if persona_id:
        if isinstance(persona_id, str):
            try:
                uuid.UUID(persona_id)
                assistant_id = persona_id
            except (ValueError, AttributeError):
                assistant_id = DEFAULT_AGENT
        else:
            assistant_id = PERSONA_ID_TO_AGENT.get(persona_id, DEFAULT_AGENT)

    if persona_id is not None and not isinstance(persona_id, str):
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
            # Pass the numeric persona_id so _handle_input reads LTM settings
            # from the correct persona, not from the underlying builtin graph key.
            llm_override = llm_override or {}
            llm_override["_persona_id"] = persona_id

    thread_metadata = thread.get("metadata") if thread else None
    resolved_project_id = _coerce_project_id(body.get("project_id"))
    if resolved_project_id is None and isinstance(thread_metadata, dict):
        resolved_project_id = _coerce_project_id(thread_metadata.get("project_id"))

    project_instructions = await resolve_project_instructions(
        user_id=project_user_id or effective_user_id,
        project_id=resolved_project_id,
        thread_metadata=thread_metadata,
    )
    llm_override = build_effective_llm_override(
        llm_override, additional_context, project_instructions
    )

    # Process file_descriptors sent by the frontend (inline base64 flow).
    # Convert each descriptor into a LangChain content block and store the raw
    # bytes in FileService so GET /api/chat/file/{id} can serve them later.
    file_descriptors: list[dict] = body.get("file_descriptors") or []
    file_content_blocks: list[dict] = []
    files_metadata: list[dict] = []

    if file_descriptors:
        import base64 as _base64

        from service.FileService import IMAGE_MIMES
        from service.FileService import store_file as _store_file
        from service.Utils import _extract_file_blocks

        for fd in file_descriptors:
            fd_id: str = fd.get("id") or str(uuid.uuid4())
            fd_name: str = fd.get("name") or "file"
            fd_mime: str = fd.get("mime_type") or "application/octet-stream"
            fd_data: str | None = fd.get("data")  # base64 string or None
            fd_type: str = fd.get("type") or "document"

            logger.debug("Processing file descriptor: id=%s, name=%s, mime=%s, has_data=%s, type=%s", fd_id, fd_name, fd_mime, bool(fd_data), fd_type)
            files_metadata.append({"id": fd_id, "type": fd_type, "name": fd_name})

            if not fd_data:
                # Try to recover file bytes from MinIO (e.g. after service restart)
                try:
                    from core.db.repositories.document_repo import DocumentRepository
                    from service.MinioService import download_file as minio_download

                    db_doc = await DocumentRepository().get_by_file_id(fd_id)
                    if db_doc and db_doc.get("minio_object_key"):
                        raw_bytes = minio_download(db_doc["minio_object_key"])
                        import base64 as _b64_inner
                        fd_data = _b64_inner.b64encode(raw_bytes).decode("ascii")
                        fd_mime = db_doc.get("mime_type") or fd_mime
                        fd_name = db_doc.get("filename") or fd_name
                        logger.debug("Recovered file %s from MinIO (%d bytes)", fd_id, len(raw_bytes))
                except Exception as _minio_err:
                    logger.warning("Could not recover file %s from MinIO: %s", fd_id, _minio_err)

            if not fd_data:
                logger.warning("File descriptor %s has no data, skipping", fd_id)
                continue

            m = fd_mime.lower().split(";")[0].strip()

            # Store raw bytes so the file-serve endpoint can return them
            try:
                raw = _base64.b64decode(fd_data)
                logger.debug("Storing file %s (%s): %d bytes", fd_id, m, len(raw))
                _store_file(fd_id, raw, fd_mime, fd_name)
            except Exception as store_err:
                logger.error("Could not store file %s in FileService: %s", fd_id, store_err, exc_info=True)

            # Persist to MinIO + DB (best-effort, only if not already saved)
            try:
                from core.db.repositories.document_repo import DocumentRepository
                from service.FileService import mime_to_chat_file_type
                from service.MinioService import upload_file as minio_upload

                doc_repo = DocumentRepository()
                existing = await doc_repo.get_by_file_id(fd_id)
                if existing is None:
                    object_key = minio_upload(
                        user_id=effective_user_id,
                        file_id=fd_id,
                        filename=fd_name,
                        data=raw,
                        mime_type=fd_mime,
                    )
                    await doc_repo.create(
                        file_id=fd_id,
                        user_id=effective_user_id,
                        filename=fd_name,
                        mime_type=fd_mime,
                        chat_file_type=mime_to_chat_file_type(fd_mime),
                        size_bytes=len(raw),
                        minio_object_key=object_key,
                        thread_id=session_id,
                        project_id=resolved_project_id,
                    )
            except Exception as _persist_err:
                logger.warning("MinIO/DB persist for inline file %s failed: %s", fd_id, _persist_err)

            if m in IMAGE_MIMES:
                file_content_blocks.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{m};base64,{fd_data}"},
                })
            else:
                blocks = _extract_file_blocks(fd_data, fd_mime, fd_name)
                file_content_blocks.extend(blocks)

    stream_input = StreamInput(
        message=message or "",
        thread_id=session_id,
        agent_id=str(assistant_id),
        agent_config=llm_override or {},
        file_content_blocks=file_content_blocks,
        files_metadata=files_metadata,
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
