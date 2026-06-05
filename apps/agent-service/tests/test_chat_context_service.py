from unittest.mock import AsyncMock, patch

import pytest

from service.ChatContextService import (
    build_effective_llm_override,
    resolve_project_instructions,
)


@pytest.mark.asyncio
async def test_resolve_project_instructions_uses_thread_metadata_fallback() -> None:
    mock_project_repo = AsyncMock()
    mock_project_repo.get_for_user.return_value = {"instructions": "  Be concise.  "}

    with patch("service.ChatContextService.ProjectRepository", return_value=mock_project_repo):
        instructions = await resolve_project_instructions(
            user_id="user-1",
            project_id=None,
            thread_metadata={"project_id": 5},
        )

    assert instructions == "Be concise."
    mock_project_repo.get_for_user.assert_awaited_once_with("user-1", 5)


def test_build_effective_llm_override_appends_project_instructions_to_agent_prompt() -> None:
    llm_override = {"system_prompt": "You are a helpful assistant."}

    merged = build_effective_llm_override(
        llm_override=llm_override,
        additional_context=None,
        project_instructions="Always answer in Turkish.",
    )

    assert merged["system_prompt"] == (
        "You are a helpful assistant.\n\n"
        "Use the following project context as high-priority guidance for this response. "
        "If there is a conflict, prioritize the latest user message.\n\n"
        "Project Instructions:\nAlways answer in Turkish."
    )
    assert llm_override == {"system_prompt": "You are a helpful assistant."}


def test_build_effective_llm_override_keeps_existing_context_without_duplication() -> None:
    merged = build_effective_llm_override(
        llm_override=None,
        additional_context="Project Instructions:\nUse short answers.",
        project_instructions="Use short answers.",
    )

    assert merged["system_prompt"] == (
        "Use the following project context as high-priority guidance for this response. "
        "If there is a conflict, prioritize the latest user message.\n\n"
        "Project Instructions:\nUse short answers."
    )