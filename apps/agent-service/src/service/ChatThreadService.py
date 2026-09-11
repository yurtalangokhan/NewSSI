"""Getting a chat turn's thread into the right shape before the run starts.

Split out of ``api/routes/ChatRoute.send_chat_message``. Creating the thread,
checking who owns it and reconciling its metadata are domain rules, so they
live here and signal refusal with ``ForbiddenError`` rather than composing an
HTTP response — the route maps that to 403.

Behaviour is unchanged from the extracted original.
"""

from __future__ import annotations

from typing import Any

from core.exceptions import ForbiddenError
from core.logger import get_logger

logger = get_logger(__name__)


async def prepare_chat_thread(
    thread_ctrl: Any,
    *,
    session_id: str,
    session_name: str,
    effective_user_id: str,
    known_user_ids: set[str],
    persona_id: Any,
    project_id: Any,
    llm_override: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return the thread for this turn, creating or reconciling it as needed.

    An existing thread owned by someone outside ``known_user_ids`` raises
    ``ForbiddenError``. An owner change *within* the known set is a legitimate
    identity migration: the previous id is kept in ``legacy_user_ids`` so old
    turns stay attributable.

    Raises:
        ForbiddenError: the thread belongs to a different user.
    """

    thread = await thread_ctrl.get_thread(session_id)

    if not thread:
        thread = await thread_ctrl.create_thread(
            thread_id=session_id,
            metadata={
                "user_id": effective_user_id,
                "name": session_name,
                "persona_id": persona_id,
                "project_id": project_id,
            },
        )
    else:
        metadata = thread.get("metadata", {}) or {}
        owner_id = metadata.get("user_id")
        if owner_id and str(owner_id) not in known_user_ids:
            raise ForbiddenError(message="chat thread belongs to another user")
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

        needs_update = (
            metadata.get("user_id") == effective_user_id and str(owner_id) != effective_user_id
        )
        if metadata.get("name") in (None, "", "New Chat"):
            metadata["name"] = session_name
            needs_update = True
        if persona_id is not None and metadata.get("persona_id") != persona_id:
            metadata["persona_id"] = persona_id
            needs_update = True
        if project_id is not None and metadata.get("project_id") != project_id:
            metadata["project_id"] = project_id
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

    return thread
