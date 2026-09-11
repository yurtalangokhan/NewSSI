"""Tests for FlowVersionRepository.publish_draft — the atomic, four-write
publish transaction (design spec 5.1, 5.2, 10).

Uses the real SQLite harness (tests/agents/storage/conftest.py) so
atomicity is proven against a genuine transaction boundary, not assumed:
16.4 forces a real IntegrityError mid-flush and asserts every one of the
four writes is absent afterward, not just the one that raised.

Brief: .tmp/flow-canvas-task-16-brief.md
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from core.db.models.agent_definition import (
    AgentDefinitionModel,
    AgentFlowVersionModel,
    FlowVersionStatus,
)
from core.exceptions import FlowVersionConflictError
from repository.flow_version_repository import FlowVersionRepository


async def _make_definition(session) -> AgentDefinitionModel:
    definition = AgentDefinitionModel(name=f"agent-{uuid4()}", graph_schema="flow")
    session.add(definition)
    await session.flush()
    await session.commit()
    return definition


@pytest.fixture
def repo(patched_repository_session) -> FlowVersionRepository:
    return FlowVersionRepository()


# ---------------------------------------------------------------------------
# 16.1 — promotes draft to published
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_promotes_draft_to_published(repo, flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    await repo.upsert_draft(definition.id, {"nodes": ["v1"]}, created_by="designer-1")

    published = await repo.publish_draft(definition.id, published_by="publisher-1")

    assert published.status == FlowVersionStatus.PUBLISHED.value
    assert published.version_no == 1
    assert published.published_by == "publisher-1"
    assert published.published_at is not None


# ---------------------------------------------------------------------------
# 16.2 — archives the previous published version
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_archives_previous_published_version(repo, flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    await repo.upsert_draft(definition.id, {"nodes": ["v1"]}, created_by="designer-1")
    await repo.publish_draft(definition.id, published_by="publisher-1")

    await repo.upsert_draft(definition.id, {"nodes": ["v2"]}, created_by="designer-1")
    await repo.publish_draft(definition.id, published_by="publisher-1")

    versions = await repo.list_versions(definition.id)
    published_rows = [v for v in versions if v.status == FlowVersionStatus.PUBLISHED.value]
    archived_rows = [v for v in versions if v.status == FlowVersionStatus.ARCHIVED.value]
    assert len(published_rows) == 1
    assert len(archived_rows) == 1
    assert published_rows[0].version_no == 2
    assert archived_rows[0].version_no == 1


# ---------------------------------------------------------------------------
# 16.3 — agent_definitions cache stays consistent with the published row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_updates_definition_cache_atomically(repo, flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    await repo.upsert_draft(definition.id, {"nodes": ["v1"]}, created_by="designer-1")
    published = await repo.publish_draft(definition.id, published_by="publisher-1")

    async with flow_version_session_factory() as session:
        refreshed = await session.get(AgentDefinitionModel, definition.id)
        assert refreshed.published_flow_version_id == published.id
        assert refreshed.flow_spec == published.flow_spec


# ---------------------------------------------------------------------------
# 16.4 — a mid-transaction failure rolls back every one of the four writes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_rolls_back_all_writes_on_failure(
    repo, flow_version_session_factory, monkeypatch
):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)
        session.add(
            AgentFlowVersionModel(
                definition_id=definition.id,
                version_no=1,
                flow_spec={"v": 1},
                status=FlowVersionStatus.PUBLISHED.value,
            )
        )
        await session.commit()

    await repo.upsert_draft(definition.id, {"v": "draft"}, created_by="designer-1")

    async def _colliding_next_version_no(_session, _definition_id):
        return 1  # collides with the already-published version_no=1

    monkeypatch.setattr(
        FlowVersionRepository, "_next_version_no", staticmethod(_colliding_next_version_no)
    )

    with pytest.raises(FlowVersionConflictError):
        await repo.publish_draft(definition.id, published_by="publisher-1")

    async with flow_version_session_factory() as session:
        refreshed_definition = await session.get(AgentDefinitionModel, definition.id)
        assert refreshed_definition.flow_spec is None
        assert refreshed_definition.published_flow_version_id is None

    draft_after = await repo.get_draft(definition.id)
    assert draft_after is not None
    assert draft_after.flow_spec == {"v": "draft"}

    published_after = await repo.get_published(definition.id)
    assert published_after is not None
    assert published_after.version_no == 1
    assert published_after.flow_spec == {"v": 1}


# ---------------------------------------------------------------------------
# 16.5 — publishing when no draft exists is a clear conflict, not a crash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_without_a_draft_raises_conflict(repo, flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    with pytest.raises(FlowVersionConflictError):
        await repo.publish_draft(definition.id, published_by="publisher-1")


@pytest.mark.asyncio
async def test_publishing_the_same_draft_twice_raises_conflict_the_second_time(
    repo, flow_version_session_factory
):
    """The realistic shape of "concurrent publish" against a single-writer
    SQLite connection: the second caller's draft is gone by the time it
    runs, and that must fail clearly rather than silently re-publish or
    corrupt history."""
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    await repo.upsert_draft(definition.id, {"nodes": ["v1"]}, created_by="designer-1")
    await repo.publish_draft(definition.id, published_by="publisher-1")

    with pytest.raises(FlowVersionConflictError):
        await repo.publish_draft(definition.id, published_by="publisher-2")


# ---------------------------------------------------------------------------
# expected_version_no optimistic-concurrency check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_with_stale_expected_version_no_raises_conflict(
    repo, flow_version_session_factory
):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    await repo.upsert_draft(definition.id, {"nodes": ["v1"]}, created_by="designer-1")
    await repo.publish_draft(definition.id, published_by="publisher-1")

    await repo.upsert_draft(definition.id, {"nodes": ["v2"]}, created_by="designer-1")

    with pytest.raises(FlowVersionConflictError):
        await repo.publish_draft(definition.id, published_by="publisher-2", expected_version_no=99)
