"""Chat context resolution service.

Responsible for:
- Fetching project-level instructions from the database.
- Merging additional_context and project instructions into the effective
  system_prompt that will be forwarded to the LLM via llm_override.

Keeping this logic here (not in the route layer) ensures it can be reused
by any chat entrypoint (send-chat-message, build/craft, etc.) and is easy
to unit-test without HTTP concerns.
"""

from __future__ import annotations

from typing import Any

from core.observability.logger import get_logger
from infrastructure.db.persistence_gateway import project_repository

logger = get_logger(__name__)


async def resolve_project_instructions(
    user_id: str,
    project_id: int | str | None,
    thread_metadata: dict[str, Any] | None = None,
) -> str | None:
    """Return the instruction text for the project, or None.

    Resolution order:
    1. Explicit ``project_id`` argument.
    2. ``project_id`` stored in ``thread_metadata`` (session-level fallback).
    """
    resolved_project_id = project_id
    if resolved_project_id is None and thread_metadata:
        resolved_project_id = thread_metadata.get("project_id")

    if resolved_project_id is None:
        return None

    try:
        project = await project_repository().get_for_user(user_id, int(resolved_project_id))
        raw = project.get("instructions") if project else None
        if isinstance(raw, str):
            return raw.strip() or None
    except Exception as exc:
        logger.debug(
            "Failed to resolve project instructions (project_id=%s): %s",
            resolved_project_id,
            exc,
        )

    return None


def build_effective_llm_override(
    llm_override: dict[str, Any] | None,
    additional_context: str | None,
    project_instructions: str | None,
) -> dict[str, Any]:
    """Merge additional_context and project_instructions into llm_override.

    - Both sources are optional; the function is a no-op when both are empty.
    - If the override already carries a system_prompt, the context block is
      appended so existing persona prompts are not discarded.
    - Returns a (shallow) copy — never mutates the input dict.
    """
    base = dict(llm_override or {})

    context_sections: list[str] = []

    if additional_context:
        context_sections.append(additional_context)

    if project_instructions and (not additional_context or project_instructions not in additional_context):
        context_sections.append(f"Project Instructions:\n{project_instructions}")

    if not context_sections:
        return base

    context_prompt = (
        "Use the following project context as high-priority guidance for this response. "
        "If there is a conflict, prioritize the latest user message.\n\n" + "\n\n".join(context_sections)
    )

    existing_system_prompt = base.get("system_prompt")
    if isinstance(existing_system_prompt, str) and existing_system_prompt.strip():
        base["system_prompt"] = f"{existing_system_prompt.strip()}\n\n{context_prompt}"
    else:
        base["system_prompt"] = context_prompt

    return base


def build_server_config(
    resolved_override: dict[str, Any] | None,
    effective_override: dict[str, Any],
) -> dict[str, Any]:
    """The run's server-side config, from the override after context is merged.

    ``system_prompt`` is only server-resolved when the persona supplied one
    (``resolved_override``); when the merged prompt is nothing but the project
    context block it is left out, so it cannot replace the agent's default
    prompt or become a system message on an agent that has none.
    """
    config = dict(effective_override)
    if not (resolved_override or {}).get("system_prompt"):
        config.pop("system_prompt", None)
    return config
