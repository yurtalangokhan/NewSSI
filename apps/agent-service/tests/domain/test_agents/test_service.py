"""Tests for agents domain service."""

import os
import sys
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
