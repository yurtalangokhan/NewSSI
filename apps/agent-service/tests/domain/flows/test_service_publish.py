"""Tests for FlowService.publish_flow — validates before publishing, then
invalidates the FlowAgent cache after the repository's transaction commits.

Uses a fake FlowVersionRepository (matching Tasks 2/4/5/6/15's DI pattern).
publish_draft's own atomicity is FlowVersionRepository's concern, already
proven against a real DB in test_publish_transaction.py (Task 16).

Spec: .tmp/flow-canvas-design.md section 5.1, 10.
Brief: .tmp/flow-canvas-task-16-brief.md
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.exceptions import FlowValidationError, FlowVersionConflictError
from domain.flows.resolvers import ResolverContext
from domain.flows.service import FlowService


def _valid_flow_dict() -> dict:
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "agent-1", "type": "ReActAgent", "values": {"system_prompt": "Be helpful."}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "agent-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "agent-1",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


def _invalid_flow_dict() -> dict:
    return {"nodes": [{"id": "out-1", "type": "ChatOutput"}], "edges": []}


class _FakeVersionRepo:
    def __init__(self, draft_spec: dict | None) -> None:
        self._draft_spec = draft_spec
        self.publish_calls: list[dict] = []
        self.published_result = SimpleNamespace(
            id=uuid4(), version_no=1, flow_spec=draft_spec, status="published"
        )

    async def get_draft(self, definition_id):
        if self._draft_spec is None:
            return None
        return SimpleNamespace(flow_spec=self._draft_spec)

    async def publish_draft(
        self, definition_id, *, published_by, expected_version_no=None, notes=None
    ):
        self.publish_calls.append(
            {
                "definition_id": definition_id,
                "published_by": published_by,
                "expected_version_no": expected_version_no,
                "notes": notes,
            }
        )
        return self.published_result


@pytest.fixture(autouse=True)
def _clear_flow_cache():
    from agents.flow_agent import _agent_cache

    _agent_cache.clear()
    yield
    _agent_cache.clear()


# ---------------------------------------------------------------------------
# 16.10 — publish rejects invalid flows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_flow_rejects_invalid_flow():
    version_repo = _FakeVersionRepo(_invalid_flow_dict())
    service = FlowService(version_repository=version_repo)
    definition_id = uuid4()

    with pytest.raises(FlowValidationError):
        await service.publish_flow(
            definition_id=definition_id,
            published_by="publisher-1",
            context=ResolverContext(user_id="u1"),
        )

    assert version_repo.publish_calls == []


# ---------------------------------------------------------------------------
# 16.5 (service level) — no draft to publish
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_flow_raises_when_no_draft_exists():
    version_repo = _FakeVersionRepo(None)
    service = FlowService(version_repository=version_repo)

    with pytest.raises(FlowVersionConflictError):
        await service.publish_flow(
            definition_id=uuid4(),
            published_by="publisher-1",
            context=ResolverContext(user_id="u1"),
        )

    assert version_repo.publish_calls == []


# ---------------------------------------------------------------------------
# Publish succeeds and invalidates the FlowAgent cache after commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_flow_invalidates_flow_agent_cache_after_publishing():
    from agents.flow_agent import cache_agent, get_cached_agent

    version_repo = _FakeVersionRepo(_valid_flow_dict())
    service = FlowService(version_repository=version_repo)
    definition_id = uuid4()

    cache_agent(str(definition_id), object())
    assert get_cached_agent(str(definition_id)) is not None

    result = await service.publish_flow(
        definition_id=definition_id,
        published_by="publisher-1",
        context=ResolverContext(user_id="u1"),
    )

    assert result is version_repo.published_result
    assert get_cached_agent(str(definition_id)) is None
    assert version_repo.publish_calls[0]["published_by"] == "publisher-1"


@pytest.mark.asyncio
async def test_publish_flow_passes_expected_version_no_through():
    version_repo = _FakeVersionRepo(_valid_flow_dict())
    service = FlowService(version_repository=version_repo)
    definition_id = uuid4()

    await service.publish_flow(
        definition_id=definition_id,
        published_by="publisher-1",
        context=ResolverContext(user_id="u1"),
        expected_version_no=3,
    )

    assert version_repo.publish_calls[0]["expected_version_no"] == 3
