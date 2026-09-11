"""Tests for FlowService.rollback_flow — no re-validation (the target
version was already validated when first published), cache invalidation
after commit, matching publish_flow's shape exactly.

Uses a fake FlowVersionRepository. rollback_to's own atomicity/append-only
behavior is proven against a real DB in test_rollback.py (Task 17).

Brief: .tmp/flow-canvas-task-17-brief.md
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from domain.flows.service import FlowService


class _FakeVersionRepo:
    def __init__(self) -> None:
        self.rollback_calls: list[dict] = []
        self.result = SimpleNamespace(id=uuid4(), version_no=3, flow_spec={"nodes": ["v1"]})

    async def rollback_to(self, definition_id, *, target_version_no, published_by):
        self.rollback_calls.append(
            {
                "definition_id": definition_id,
                "target_version_no": target_version_no,
                "published_by": published_by,
            }
        )
        return self.result


@pytest.fixture(autouse=True)
def _clear_flow_cache():
    from agents.flow_agent import _agent_cache

    _agent_cache.clear()
    yield
    _agent_cache.clear()


@pytest.mark.asyncio
async def test_rollback_flow_delegates_to_repository_and_returns_result():
    version_repo = _FakeVersionRepo()
    service = FlowService(version_repository=version_repo)
    definition_id = uuid4()

    result = await service.rollback_flow(
        definition_id=definition_id, target_version_no=1, published_by="publisher-1"
    )

    assert result is version_repo.result
    assert version_repo.rollback_calls[0] == {
        "definition_id": definition_id,
        "target_version_no": 1,
        "published_by": "publisher-1",
    }


@pytest.mark.asyncio
async def test_rollback_flow_invalidates_flow_agent_cache_after_rollback():
    from agents.flow_agent import cache_agent, get_cached_agent

    version_repo = _FakeVersionRepo()
    service = FlowService(version_repository=version_repo)
    definition_id = uuid4()

    cache_agent(str(definition_id), object())
    assert get_cached_agent(str(definition_id)) is not None

    await service.rollback_flow(
        definition_id=definition_id, target_version_no=1, published_by="publisher-1"
    )

    assert get_cached_agent(str(definition_id)) is None
