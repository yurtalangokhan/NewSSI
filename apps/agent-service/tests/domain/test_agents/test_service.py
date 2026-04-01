"""Tests for agents domain service."""

import pytest
import sys
import os

# Ensure src is in the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))


class TestAgentService:
    """Test suite for AgentService."""

    def test_service_import(self):
        """Test that agent service can be imported."""
        from domain.agents.service import AgentService

        assert AgentService is not None


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
