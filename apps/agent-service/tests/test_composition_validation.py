"""Tests for CompositionValidationService."""

from uuid import uuid4

import pytest

from service.CompositionValidationService import (
    CompositionValidationService,
)


# Mock fixtures
class MockAgent:
    """Mock agent model for testing."""

    def __init__(self, agent_id, name, graph_schema, sub_agent_ids=None):
        self.id = agent_id
        self.name = name
        self.graph_schema = graph_schema
        self.sub_agent_ids = sub_agent_ids or []

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "graph_schema": self.graph_schema,
            "sub_agent_ids": self.sub_agent_ids,
        }


class MockRepository:
    """Mock repository for testing."""

    def __init__(self, agents=None):
        self.agents = agents or {}

    async def get_by_id(self, agent_id):
        return self.agents.get(agent_id)

    async def find_agents_by_sub_agent_id(self, sub_agent_id):
        """Find all agents referencing sub_agent_id."""
        result = []
        for agent in self.agents.values():
            if sub_agent_id in agent.sub_agent_ids:
                result.append(agent.id)
        return result


# Tests
@pytest.mark.asyncio
async def test_validate_references_exist_valid():
    """All sub-agents exist."""
    agent_a = MockAgent(uuid4(), "Agent A", "REACT")
    agent_b = MockAgent(uuid4(), "Agent B", "REACT")

    repo = MockRepository({agent_a.id: agent_a, agent_b.id: agent_b})
    service = CompositionValidationService(repo)

    valid, errors = await service.validate_references_exist([agent_a.id, agent_b.id])

    assert valid is True
    assert errors == []


@pytest.mark.asyncio
async def test_validate_references_exist_missing():
    """One sub-agent is missing."""
    agent_a = MockAgent(uuid4(), "Agent A", "REACT")
    missing_id = uuid4()

    repo = MockRepository({agent_a.id: agent_a})
    service = CompositionValidationService(repo)

    valid, errors = await service.validate_references_exist([agent_a.id, missing_id])

    assert valid is False
    assert len(errors) == 1
    assert "does not exist" in errors[0]


@pytest.mark.asyncio
async def test_validate_references_exist_too_many():
    """Too many sub-agents (exceeds MAX_SUB_AGENTS)."""
    ids = [uuid4() for _ in range(25)]  # Assume MAX_SUB_AGENTS = 20

    repo = MockRepository({})
    service = CompositionValidationService(repo)

    valid, errors = await service.validate_references_exist(ids)

    assert valid is False
    assert "Too many sub-agents" in errors[0]


@pytest.mark.asyncio
async def test_detect_circular_dependency_direct():
    """A→B→A circular dependency."""
    agent_a_id = uuid4()
    agent_b_id = uuid4()

    agent_a = MockAgent(agent_a_id, "Agent A", "SUPERVISOR", [agent_b_id])
    agent_b = MockAgent(agent_b_id, "Agent B", "REACT", [agent_a_id])  # B points back to A

    repo = MockRepository({agent_a_id: agent_a, agent_b_id: agent_b})
    service = CompositionValidationService(repo)

    # When checking if A with sub_agents=[B] is valid
    is_circular = await service.detect_circular_dependency(agent_a_id, [agent_b_id])

    assert is_circular is True


@pytest.mark.asyncio
async def test_detect_circular_dependency_indirect():
    """A→B→C→A circular dependency (3-level cycle)."""
    agent_a_id = uuid4()
    agent_b_id = uuid4()
    agent_c_id = uuid4()

    agent_a = MockAgent(agent_a_id, "A", "SUPERVISOR", [agent_b_id])
    agent_b = MockAgent(agent_b_id, "B", "SUPERVISOR", [agent_c_id])
    agent_c = MockAgent(agent_c_id, "C", "REACT", [agent_a_id])  # C → A

    repo = MockRepository({agent_a_id: agent_a, agent_b_id: agent_b, agent_c_id: agent_c})
    service = CompositionValidationService(repo)

    is_circular = await service.detect_circular_dependency(agent_a_id, [agent_b_id])

    assert is_circular is True


@pytest.mark.asyncio
async def test_detect_circular_dependency_none():
    """No circular dependency: A→B→C (linear chain)."""
    agent_a_id = uuid4()
    agent_b_id = uuid4()
    agent_c_id = uuid4()

    agent_a = MockAgent(agent_a_id, "A", "SUPERVISOR", [agent_b_id])
    agent_b = MockAgent(agent_b_id, "B", "REACT", [agent_c_id])
    agent_c = MockAgent(agent_c_id, "C", "REACT", [])

    repo = MockRepository({agent_a_id: agent_a, agent_b_id: agent_b, agent_c_id: agent_c})
    service = CompositionValidationService(repo)

    is_circular = await service.detect_circular_dependency(agent_a_id, [agent_b_id])

    assert is_circular is False


@pytest.mark.asyncio
async def test_validate_schema_compatibility_supervisor_with_react():
    """SUPERVISOR with REACT sub-agents is valid."""
    sub_agent = MockAgent(uuid4(), "Sub", "REACT", [])

    repo = MockRepository({sub_agent.id: sub_agent})
    service = CompositionValidationService(repo)

    valid, errors = await service.validate_schema_compatibility("SUPERVISOR", [sub_agent.id])

    assert valid is True
    assert errors == []


@pytest.mark.asyncio
async def test_validate_schema_compatibility_supervisor_with_zero_shot():
    """SUPERVISOR cannot use ZERO_SHOT sub-agents (no tools)."""
    sub_agent = MockAgent(uuid4(), "Sub", "ZERO_SHOT", [])

    repo = MockRepository({sub_agent.id: sub_agent})
    service = CompositionValidationService(repo)

    valid, errors = await service.validate_schema_compatibility("SUPERVISOR", [sub_agent.id])

    assert valid is False
    assert len(errors) > 0
    assert "tools" in errors[0].lower() or "zero_shot" in errors[0].lower()


@pytest.mark.asyncio
async def test_validate_schema_compatibility_pipeline_with_supervisor():
    """PIPELINE cannot use SUPERVISOR sub-agents (nested multi-agent)."""
    sub_agent = MockAgent(uuid4(), "Sub", "SUPERVISOR", [])

    repo = MockRepository({sub_agent.id: sub_agent})
    service = CompositionValidationService(repo)

    valid, errors = await service.validate_schema_compatibility("PIPELINE", [sub_agent.id])

    assert valid is False
    assert len(errors) > 0
    assert "nested" in errors[0].lower() or "supervisor" in errors[0].lower()


@pytest.mark.asyncio
async def test_get_composition_depth_async_leaf():
    """Leaf agent (no sub-agents) has depth 0."""
    agent = MockAgent(uuid4(), "Leaf", "REACT", [])

    repo = MockRepository({agent.id: agent})
    service = CompositionValidationService(repo)

    depth = await service.get_composition_depth_async(agent.id)

    assert depth == 0


@pytest.mark.asyncio
async def test_get_composition_depth_async_linear():
    """A→B→C chain has depth 2."""
    agent_c = MockAgent(uuid4(), "C", "REACT", [])
    agent_b = MockAgent(uuid4(), "B", "REACT", [agent_c.id])
    agent_a = MockAgent(uuid4(), "A", "SUPERVISOR", [agent_b.id])

    repo = MockRepository({agent_a.id: agent_a, agent_b.id: agent_b, agent_c.id: agent_c})
    service = CompositionValidationService(repo)

    depth = await service.get_composition_depth_async(agent_a.id)

    assert depth == 2


@pytest.mark.asyncio
async def test_get_composition_depth_async_branching():
    """A→[B, C, D] (parallel) has depth 1."""
    agent_b = MockAgent(uuid4(), "B", "REACT", [])
    agent_c = MockAgent(uuid4(), "C", "REACT", [])
    agent_d = MockAgent(uuid4(), "D", "REACT", [])
    agent_a = MockAgent(uuid4(), "A", "SUPERVISOR", [agent_b.id, agent_c.id, agent_d.id])

    repo = MockRepository(
        {
            agent_a.id: agent_a,
            agent_b.id: agent_b,
            agent_c.id: agent_c,
            agent_d.id: agent_d,
        }
    )
    service = CompositionValidationService(repo)

    depth = await service.get_composition_depth_async(agent_a.id)

    assert depth == 1


@pytest.mark.asyncio
async def test_get_composition_depth_async_complex():
    """A→[B, C] where B→D has depth 2."""
    agent_d = MockAgent(uuid4(), "D", "REACT", [])
    agent_b = MockAgent(uuid4(), "B", "REACT", [agent_d.id])
    agent_c = MockAgent(uuid4(), "C", "REACT", [])
    agent_a = MockAgent(uuid4(), "A", "SUPERVISOR", [agent_b.id, agent_c.id])

    repo = MockRepository(
        {
            agent_a.id: agent_a,
            agent_b.id: agent_b,
            agent_c.id: agent_c,
            agent_d.id: agent_d,
        }
    )
    service = CompositionValidationService(repo)

    depth = await service.get_composition_depth_async(agent_a.id)

    assert depth == 2


@pytest.mark.asyncio
async def test_validate_max_depth_within_limit():
    """Depth within MAX_DEPTH (5) is valid."""
    agent_5 = MockAgent(uuid4(), "5", "REACT", [])
    agent_4 = MockAgent(uuid4(), "4", "REACT", [agent_5.id])
    agent_3 = MockAgent(uuid4(), "3", "REACT", [agent_4.id])
    agent_2 = MockAgent(uuid4(), "2", "REACT", [agent_3.id])
    agent_1 = MockAgent(uuid4(), "1", "SUPERVISOR", [agent_2.id])

    repo = MockRepository(
        {
            agent_1.id: agent_1,
            agent_2.id: agent_2,
            agent_3.id: agent_3,
            agent_4.id: agent_4,
            agent_5.id: agent_5,
        }
    )
    service = CompositionValidationService(repo)

    valid, errors = await service.validate_max_depth(None, [agent_2.id])

    assert valid is True
    assert errors == []


@pytest.mark.asyncio
async def test_validate_max_depth_update_uses_proposed_sub_agents():
    """Updating an existing leaf with a deep child should validate the proposed depth."""
    agent_5 = MockAgent(uuid4(), "5", "REACT", [])
    agent_4 = MockAgent(uuid4(), "4", "SUPERVISOR", [agent_5.id])
    agent_3 = MockAgent(uuid4(), "3", "SUPERVISOR", [agent_4.id])
    agent_2 = MockAgent(uuid4(), "2", "SUPERVISOR", [agent_3.id])
    agent_1 = MockAgent(uuid4(), "1", "SUPERVISOR", [agent_2.id])
    root = MockAgent(uuid4(), "Root", "SUPERVISOR", [])

    repo = MockRepository(
        {
            root.id: root,
            agent_1.id: agent_1,
            agent_2.id: agent_2,
            agent_3.id: agent_3,
            agent_4.id: agent_4,
            agent_5.id: agent_5,
        }
    )
    service = CompositionValidationService(repo)

    valid, errors = await service.validate_max_depth(root.id, [agent_1.id])

    assert valid is False
    assert "exceed limit" in errors[0]


@pytest.mark.asyncio
async def test_validate_full_composition_valid():
    """Full validation with all checks passing."""
    agent_b = MockAgent(uuid4(), "Sub", "REACT", [])

    repo = MockRepository({agent_b.id: agent_b})
    service = CompositionValidationService(repo)

    result = await service.validate_full_composition(
        agent_id=None,  # Creating new
        graph_schema="SUPERVISOR",
        sub_agent_ids=[agent_b.id],
    )

    assert result.valid is True
    assert result.errors == []
    assert result.depth == 1


@pytest.mark.asyncio
async def test_validate_full_composition_invalid():
    """Full validation catches multiple errors."""
    agent_b = MockAgent(uuid4(), "Sub", "ZERO_SHOT", [])  # Incompatible with SUPERVISOR
    agent_a_id = uuid4()
    agent_a = MockAgent(agent_a_id, "Master", "SUPERVISOR", [agent_b.id])

    # Setup circular: A points to B, B points to A
    agent_b.sub_agent_ids = [agent_a_id]

    repo = MockRepository({agent_a_id: agent_a, agent_b.id: agent_b})
    service = CompositionValidationService(repo)

    result = await service.validate_full_composition(
        agent_id=agent_a_id,
        graph_schema="SUPERVISOR",
        sub_agent_ids=[agent_b.id],
    )

    assert result.valid is False
    assert len(result.errors) >= 2  # Circular + schema mismatch
