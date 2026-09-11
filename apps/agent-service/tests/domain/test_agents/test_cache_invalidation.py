"""Tests for the cache-invalidation bug found during P3 planning.

domain/agents/service.py's update/delete paths invalidated only
agents.dynamic_agent's cache, unconditionally — but P2 Task 13 gave
FlowAgent its own, separate cache module. A flow-backed definition updated
or deleted through AgentDefinitionService kept serving its previously
compiled graph until process restart, because the invalidation call cleared
an entry in the wrong cache dict.

Brief: .tmp/flow-canvas-task-16-brief.md ("Cache coherence — and a real bug
to fix first").
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from domain.agents.service import AgentDefinitionService


class _FakeRepo:
    def __init__(self, definition):
        self._definition = definition
        self.deleted = False

    async def get_by_id(self, _id):
        return self._definition

    async def update(self, _id, updates):
        for key, value in updates.items():
            setattr(self._definition, key, value)
        return self._definition

    async def delete(self, _id):
        self.deleted = True
        return True


def _flow_definition(definition_id):
    return SimpleNamespace(
        id=definition_id,
        graph_schema="flow",
        sub_agent_config_version=0,
    )


def _classic_definition(definition_id):
    return SimpleNamespace(
        id=definition_id,
        graph_schema="react",
        sub_agent_config_version=0,
    )


@pytest.fixture(autouse=True)
def _clear_caches():
    from agents.dynamic_agent import _agent_cache as dynamic_cache
    from agents.flow_agent import _agent_cache as flow_cache

    dynamic_cache.clear()
    flow_cache.clear()
    yield
    dynamic_cache.clear()
    flow_cache.clear()


# ---------------------------------------------------------------------------
# 16.7 / 16.8 — the bug: flow-backed cache must actually be cleared
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_updating_flow_backed_definition_invalidates_flow_agent_cache():
    from agents.flow_agent import cache_agent as cache_flow_agent
    from agents.flow_agent import get_cached_agent as get_cached_flow_agent

    definition_id = uuid4()
    definition = _flow_definition(definition_id)
    repo = _FakeRepo(definition)
    service = AgentDefinitionService(repo)

    cache_flow_agent(str(definition_id), object())
    assert get_cached_flow_agent(str(definition_id)) is not None

    await service.update_agent_definition(definition_id, {"name": "renamed"})

    assert get_cached_flow_agent(str(definition_id)) is None


@pytest.mark.asyncio
async def test_deleting_flow_backed_definition_invalidates_flow_agent_cache():
    from agents.flow_agent import cache_agent as cache_flow_agent
    from agents.flow_agent import get_cached_agent as get_cached_flow_agent

    definition_id = uuid4()
    definition = _flow_definition(definition_id)
    repo = _FakeRepo(definition)
    service = AgentDefinitionService(repo)

    cache_flow_agent(str(definition_id), object())

    await service.delete_agent_definition(definition_id)

    assert get_cached_flow_agent(str(definition_id)) is None
    assert repo.deleted is True


@pytest.mark.asyncio
async def test_updating_flow_backed_definition_does_not_touch_dynamic_agent_cache():
    """The old bug's mirror image: updating a flow-backed agent must not
    evict an unrelated DynamicAgent cache entry that happens to share an id
    space — cross-contamination in either direction is wrong."""
    from agents.dynamic_agent import cache_agent as cache_dynamic_agent
    from agents.dynamic_agent import get_cached_agent as get_cached_dynamic_agent

    definition_id = uuid4()
    other_id = str(uuid4())
    definition = _flow_definition(definition_id)
    repo = _FakeRepo(definition)
    service = AgentDefinitionService(repo)

    cache_dynamic_agent(other_id, object())

    await service.update_agent_definition(definition_id, {"name": "renamed"})

    assert get_cached_dynamic_agent(other_id) is not None


# ---------------------------------------------------------------------------
# 16.9 — constraint #1: the classic path's own behavior is unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_updating_classic_agent_invalidates_dynamic_agent_cache_unchanged():
    from agents.dynamic_agent import cache_agent as cache_dynamic_agent
    from agents.dynamic_agent import get_cached_agent as get_cached_dynamic_agent

    definition_id = uuid4()
    definition = _classic_definition(definition_id)
    repo = _FakeRepo(definition)
    service = AgentDefinitionService(repo)

    cache_dynamic_agent(str(definition_id), object())
    assert get_cached_dynamic_agent(str(definition_id)) is not None

    await service.update_agent_definition(definition_id, {"name": "renamed"})

    assert get_cached_dynamic_agent(str(definition_id)) is None


@pytest.mark.asyncio
async def test_deleting_classic_agent_invalidates_dynamic_agent_cache_unchanged():
    from agents.dynamic_agent import cache_agent as cache_dynamic_agent
    from agents.dynamic_agent import get_cached_agent as get_cached_dynamic_agent

    definition_id = uuid4()
    definition = _classic_definition(definition_id)
    repo = _FakeRepo(definition)
    service = AgentDefinitionService(repo)

    cache_dynamic_agent(str(definition_id), object())

    await service.delete_agent_definition(definition_id)

    assert get_cached_dynamic_agent(str(definition_id)) is None
