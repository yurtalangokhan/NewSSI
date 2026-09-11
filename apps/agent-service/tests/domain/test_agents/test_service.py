"""Tests for agents domain service."""

import os
import sys
from dataclasses import dataclass
from uuid import uuid4

import pytest

# Ensure src is in the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))


class TestAgentService:
    """Test suite for AgentService."""

    def test_service_import(self):
        """Test that agent service can be imported."""
        from domain.agents.service import AgentService

        assert AgentService is not None


@dataclass
class _FakeDefinitionForPreview:
    model: str | None = None
    mcp_tools: list | None = None
    memory_type: str | None = None
    system_prompt: str | None = None


class TestBuildAgentPreviewText:
    """build_agent_preview_text() summarizes an agent's model/tools/memory/prompt for hover previews."""

    def test_includes_model_tool_count_and_memory_state(self):
        from domain.agents.service import build_agent_preview_text

        d = _FakeDefinitionForPreview(
            model="gpt-4o",
            mcp_tools=["file_read", "git_status"],
            memory_type="long_term",
        )

        text = build_agent_preview_text(d)

        assert "gpt-4o" in text
        assert "Tools: 2" in text
        assert "Memory: on" in text

    def test_reports_memory_off_when_memory_type_is_none_or_missing(self):
        from domain.agents.service import build_agent_preview_text

        d = _FakeDefinitionForPreview(model="gpt-4o", mcp_tools=[], memory_type="none")

        text = build_agent_preview_text(d)

        assert "Memory: off" in text

    def test_appends_truncated_system_prompt(self):
        from domain.agents.service import build_agent_preview_text

        d = _FakeDefinitionForPreview(system_prompt="x" * 300)

        text = build_agent_preview_text(d)

        prompt_line = text.splitlines()[1]
        assert len(prompt_line) <= 160
        assert prompt_line.endswith("...")

    def test_omits_prompt_line_when_system_prompt_is_empty(self):
        from domain.agents.service import build_agent_preview_text

        d = _FakeDefinitionForPreview(system_prompt=None)

        text = build_agent_preview_text(d)

        assert "\n" not in text

    def test_tolerates_objects_missing_the_preview_fields(self):
        """Some callers (e.g. minimal test doubles simulating a partial
        agent definition) may not define model/mcp_tools/memory_type/
        system_prompt at all — the summary must degrade gracefully rather
        than raising AttributeError."""
        from types import SimpleNamespace

        from domain.agents.service import build_agent_preview_text

        d = SimpleNamespace(id="c-1", name="Classic Agent", graph_schema="react")

        text = build_agent_preview_text(d)

        assert "Model: default" in text
        assert "Tools: 0" in text
        assert "Memory: off" in text


class FakeAgentDefinitionRepository:
    """Minimal repository double for AgentDefinitionService tests."""

    def __init__(self, agents=None):
        self.agents = agents or {}
        self.created_kwargs = None

    async def get_by_name(self, _name):
        return None

    async def get_by_id(self, agent_id):
        return self.agents.get(agent_id)

    async def create(self, **kwargs):
        self.created_kwargs = kwargs
        return kwargs


class TestAgentDefinitionService:
    """Test suite for dynamic agent definition behavior."""

    @pytest.mark.asyncio
    async def test_create_agent_definition_persists_sub_agent_ids(self):
        """Create should validate and persist referenced sub-agent IDs."""
        from domain.agents.service import AgentDefinitionService

        sub_agent_id = uuid4()
        sub_agent = type(
            "SubAgent",
            (),
            {
                "id": sub_agent_id,
                "name": "Researcher",
                "graph_schema": "REACT",
                "sub_agent_ids": [],
            },
        )()
        repo = FakeAgentDefinitionRepository({sub_agent_id: sub_agent})
        service = AgentDefinitionService(repo)

        await service.create_agent_definition(
            name="Supervisor",
            graph_schema="supervisor",
            sub_agent_ids=[sub_agent_id],
        )

        assert repo.created_kwargs["sub_agent_ids"] == [sub_agent_id]


class TestAgentRegistry:
    """Test suite for agent registry."""

    def test_agents_module_import(self):
        """Test that agents module imports correctly."""
        import agents as agents_module

        assert hasattr(agents_module, "agents")

    def test_default_agent_defined(self):
        """Test default agent is defined."""
        from agents import DEFAULT_AGENT

        assert DEFAULT_AGENT is not None
