"""Pure helpers for the user controller.

Extracted from ``UserController`` to reduce its LOC.  All functions here
are stateless.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def file_chat_type(content_type: str | None, filename: str) -> str:
    mime = (content_type or "").lower()
    lower_name = filename.lower()
    if mime.startswith("image/"):
        return "image"
    if mime in {"text/csv", "application/csv"} or lower_name.endswith(".csv"):
        return "csv"
    if mime.startswith("text/") or lower_name.endswith((".txt", ".md")):
        return "plain_text"
    return "document"


def thread_project_id(thread: dict[str, Any]) -> int | None:
    project_id = thread.get("project_id")
    if project_id is None:
        metadata = thread.get("metadata", {}) or {}
        project_id = metadata.get("project_id")
    if project_id is None:
        return None
    try:
        return int(project_id)
    except (TypeError, ValueError):
        return None


def normalize_owner_ids(user_id: str, owner_ids: list[str] | None = None) -> list[str]:
    normalized: list[str] = []
    for candidate in [user_id, *(owner_ids or [])]:
        if not candidate:
            continue
        candidate_id = str(candidate)
        if candidate_id not in normalized:
            normalized.append(candidate_id)
    return normalized


def thread_belongs_to_owner_ids(thread: dict[str, Any], owner_ids: list[str]) -> bool:
    metadata = thread.get("metadata", {}) or {}
    owner = metadata.get("user_id")
    if owner and str(owner) in owner_ids:
        return True

    legacy_owner_ids = metadata.get("legacy_user_ids") or []
    if isinstance(legacy_owner_ids, list):
        return any(str(candidate) in owner_ids for candidate in legacy_owner_ids)

    return False


def chat_session_activity_time(session: dict[str, Any]) -> str:
    """Return the backwards-compatible product activity time for a session."""
    if "last_message_at" in session:
        return session.get("last_message_at") or session.get("time_created") or ""
    return session.get("time_updated") or session.get("time_created") or ""


def serialize_chat_session(thread: dict[str, Any]) -> dict[str, Any]:
    metadata = thread.get("metadata", {}) or {}
    session_name = metadata.get("name") or "New Chat"
    return {
        "id": thread.get("thread_id", ""),
        "name": session_name,
        "description": session_name,
        "persona_id": metadata.get("persona_id", 0),
        "time_created": thread.get("created_at"),
        "time_updated": thread.get("updated_at"),
        "last_message_at": thread.get("last_message_at"),
        "last_accessed_at": thread.get("last_accessed_at"),
        "shared_status": "private",
        "project_id": thread_project_id(thread),
        "current_alternate_model": metadata.get("current_alternate_model", ""),
        "current_temperature_override": metadata.get("current_temperature_override"),
    }


def serialize_admin_provider(provider: dict[str, Any]) -> dict[str, Any]:
    """Serialize a provider for the admin endpoint."""
    return {
        "id": provider.get("id"),
        "name": provider.get("name"),
        "provider": provider.get("provider"),
        "provider_display_name": provider.get("provider_display_name"),
        "api_key": None,
        "api_base": None,
        "api_version": None,
        "custom_config": {},
        "is_public": True,
        "is_auto_mode": False,
        "groups": [],
        "personas": [],
        "deployment_name": None,
        "model_configurations": provider.get("model_configurations", []),
    }
