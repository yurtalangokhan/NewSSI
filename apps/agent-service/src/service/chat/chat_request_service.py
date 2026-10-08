"""Reading a chat turn's request: who is asking, and what they asked for.

Split out of ``api/routes/chat_route.send_chat_message``. Identity resolution
walks several id spaces (Keycloak subject, service user id, projects user id)
and the request body carries a dozen optional fields; both were inline in the
route, which is what let one handler reach 445 lines.

Behaviour is unchanged from the extracted original.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import uuid

from localization import t
from pydantic import ValidationError as PydanticValidationError

from core.exceptions import ValidationFailedError
from core.observability.logger import get_logger
from schemas.chat import DocumentContext

logger = get_logger(__name__)


@dataclass
class ChatIdentity:
    """Who this turn belongs to.

    ``known_user_ids`` is every id that may legitimately own the thread — the
    same person can appear under a Keycloak subject, a service user id and a
    projects user id, and a thread created under one must stay reachable from
    the others.
    """

    effective_user_id: str
    known_user_ids: set[str] = field(default_factory=set)
    project_user_id: str | None = None


@dataclass
class ChatRequestFields:
    """The parts of the request body this endpoint acts on."""

    message: str
    chat_session_id: Any | None
    persona_id: Any | None
    llm_override: dict[str, Any] | None
    additional_context: str | None
    document_context: DocumentContext | None = None


async def resolve_chat_identity(
    identity: dict[str, Any],
    fallback_user_id: str,  # noqa: ARG001
    effective_user_id: str,
    user_service: Any = None,
) -> ChatIdentity:
    """Collect every id that may own this turn's thread."""
    known_user_ids = {
        str(candidate) for candidate in (identity.get("known_user_ids") or [effective_user_id]) if candidate
    }
    known_user_ids.add(effective_user_id)

    svc = user_service
    project_user_id = await svc.resolve_projects_user_id(str(identity.get("keycloak_id") or effective_user_id))
    if project_user_id:
        known_user_ids.add(str(project_user_id))

    return ChatIdentity(
        effective_user_id=effective_user_id,
        known_user_ids=known_user_ids,
        project_user_id=str(project_user_id) if project_user_id else None,
    )


def _parse_document_context(raw: Any) -> DocumentContext | None:
    """Validate the client-sent ``document_context``, if any.

    Unlike ``chat_session_id`` (repaired silently -- a bad thread id is
    replaced with a fresh one so the turn still succeeds), a malformed
    document reference is rejected outright: silently dropping it would make
    the "edit this document" feature look like it worked while agents never
    saw it, which is worse than a clear 4xx. Mirrors the
    ``agent.reserved_keys_in_config`` validation in
    ``agent_runner_coordinator.py`` -- a domain ``ValidationFailedError`` the
    app's registered error handler already turns into a 422 response, so the
    route stays thin.
    """
    if raw is None:
        return None
    try:
        return DocumentContext.model_validate(raw)
    except PydanticValidationError as exc:
        raise ValidationFailedError(
            code="chat.invalid_document_context",
            message=t("chat.invalid_document_context", error=str(exc)),
            details={"errors": exc.errors(include_url=False)},
        ) from exc


def parse_chat_request(body: dict[str, Any]) -> ChatRequestFields:
    """Pull the acted-on fields out of the request body.

    ``additional_context`` is normalised to None when blank so downstream code
    can test it for truthiness rather than re-stripping it.
    """
    additional_context = body.get("additional_context")
    additional_context = additional_context.strip() or None if isinstance(additional_context, str) else None

    return ChatRequestFields(
        message=body.get("message") if body.get("message") is not None else "",
        chat_session_id=body.get("chat_session_id"),
        persona_id=body.get("persona_id"),
        llm_override=body.get("llm_override"),
        additional_context=additional_context,
        document_context=_parse_document_context(body.get("document_context")),
    )


def resolve_session_id(chat_session_id: Any | None) -> str:
    """A valid thread id for this turn, minting one when the client's is unusable.

    A malformed id is replaced rather than rejected: the client gets a working
    conversation instead of an error it cannot act on, and the bad id never
    reaches the checkpointer.
    """
    session_id = chat_session_id
    if not session_id:
        session_id = str(uuid.uuid4())
        logger.info("Generated new session_id: %s", session_id)

    try:
        uuid.UUID(session_id)
    except (ValueError, AttributeError):
        session_id = str(uuid.uuid4())
        logger.warning("Invalid session_id provided, generated new: %s", session_id)

    return str(session_id)
