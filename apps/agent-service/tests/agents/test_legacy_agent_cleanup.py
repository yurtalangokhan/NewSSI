"""Regression coverage for removing unreachable legacy agent modules."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from controller.session_controller import AGENT_TO_PERSONA_ID
from service.AssistantSchemasService import AssistantSchemasService

AGENTS_SRC = Path(__file__).parents[2] / "src" / "agents"


def test_unreachable_legacy_agent_modules_are_removed() -> None:
    """Runtime-unreachable root agents must not remain as dead source files."""
    removed_paths = [
        AGENTS_SRC / "command_agent.py",
        AGENTS_SRC / "interrupt_agent.py",
        AGENTS_SRC / "knowledge_base_agent.py",
        AGENTS_SRC / "langgraph_supervisor_agent.py",
        AGENTS_SRC / "langgraph_supervisor_hierarchy_agent.py",
        AGENTS_SRC / "bg_task_agent",
    ]

    for path in removed_paths:
        assert not path.exists(), f"{path.relative_to(AGENTS_SRC)} must stay removed"


def test_session_persona_mapping_lists_only_public_runtime_agents() -> None:
    """Legacy numeric persona aliases must not advertise missing agent modules."""
    assert AGENT_TO_PERSONA_ID == {
        "chatbot": 0,
        "configurable-mcp-agent": 1,
    }


@pytest.mark.asyncio
async def test_assistant_schemas_do_not_publish_removed_agent_keys() -> None:
    """Schema lookup should not expose configuration for unavailable agents."""
    service = AssistantSchemasService()
    service.get_ollama_models = AsyncMock(return_value=["test-model"])  # type: ignore[method-assign]

    removed_keys = [
        "command-agent",
        "bg-task-agent",
        "langgraph-supervisor-agent",
        "langgraph-supervisor-hierarchy-agent",
    ]

    for key in removed_keys:
        assert await service.get_assistant_schemas(key) == {}

    assert await service.get_assistant_schemas("configurable-mcp-agent") != {}
