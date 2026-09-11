"""Tests for FlowVersionRepository.rollback_to — append-only restoration of
a previously published version (design spec 5.3).

Rollback never mutates the target row; it creates a NEW published version
whose flow_spec is a copy of the target's, then archives whatever was
published before. Reuses publish_draft's transaction shape (Task 16) —
same real SQLite harness, same atomicity guarantee.

Brief: .tmp/flow-canvas-task-17-brief.md
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from core.db.models.agent_definition import AgentDefinitionModel, FlowVersionStatus
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
# 17.1 — creates a new version with the copied spec
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_creates_new_version_with_copied_spec(repo, flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    await repo.upsert_draft(definition.id, {"nodes": ["v1"]}, created_by="designer-1")
    await repo.publish_draft(definition.id, published_by="publisher-1")
    await repo.upsert_draft(definition.id, {"nodes": ["v2"]}, created_by="designer-1")
    await repo.publish_draft(definition.id, published_by="publisher-1")

    restored = await repo.rollback_to(
        definition.id, target_version_no=1, published_by="publisher-2"
    )

    assert restored.version_no == 3
    assert restored.flow_spec == {"nodes": ["v1"]}
    assert restored.status == FlowVersionStatus.PUBLISHED.value


# ---------------------------------------------------------------------------
# 17.2 — the target row is never mutated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_does_not_mutate_target_version(repo, flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    await repo.upsert_draft(definition.id, {"nodes": ["v1"]}, created_by="designer-1")
    await repo.publish_draft(definition.id, published_by="publisher-1")

    await repo.upsert_draft(definition.id, {"nodes": ["v2"]}, created_by="designer-1")
    await repo.publish_draft(definition.id, published_by="publisher-1")

    # Snapshot taken once v1 has settled into its final pre-rollback state
    # (archived by the second publish) — the reference point for "unchanged
    # by rollback" is v1's state right before rollback runs, not its
    # transient "just published" state from two steps ago.
    target_before = await repo.get_by_version_no(definition.id, 1)

    await repo.rollback_to(definition.id, target_version_no=1, published_by="publisher-2")

    target_after = await repo.get_by_version_no(definition.id, 1)
    assert target_after.status == target_before.status  # still "archived", unchanged
    assert target_after.version_no == 1
    assert target_after.published_at == target_before.published_at


# ---------------------------------------------------------------------------
# 17.3 — archives whatever was published before the rollback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_archives_current_published(repo, flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    await repo.upsert_draft(definition.id, {"nodes": ["v1"]}, created_by="designer-1")
    await repo.publish_draft(definition.id, published_by="publisher-1")
    await repo.upsert_draft(definition.id, {"nodes": ["v2"]}, created_by="designer-1")
    await repo.publish_draft(definition.id, published_by="publisher-1")

    await repo.rollback_to(definition.id, target_version_no=1, published_by="publisher-2")

    versions = await repo.list_versions(definition.id)
    published_rows = [v for v in versions if v.status == FlowVersionStatus.PUBLISHED.value]
    assert len(published_rows) == 1
    assert published_rows[0].version_no == 3


# ---------------------------------------------------------------------------
# 17.4 — agent_definitions cache reflects the restored version
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_updates_definition_cache(repo, flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    await repo.upsert_draft(definition.id, {"nodes": ["v1"]}, created_by="designer-1")
    await repo.publish_draft(definition.id, published_by="publisher-1")
    await repo.upsert_draft(definition.id, {"nodes": ["v2"]}, created_by="designer-1")
    await repo.publish_draft(definition.id, published_by="publisher-1")

    restored = await repo.rollback_to(
        definition.id, target_version_no=1, published_by="publisher-2"
    )

    async with flow_version_session_factory() as session:
        refreshed = await session.get(AgentDefinitionModel, definition.id)
        assert refreshed.published_flow_version_id == restored.id
        assert refreshed.flow_spec == {"nodes": ["v1"]}


# ---------------------------------------------------------------------------
# 17.5 — an existing draft survives rollback untouched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_preserves_existing_draft(repo, flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    await repo.upsert_draft(definition.id, {"nodes": ["v1"]}, created_by="designer-1")
    await repo.publish_draft(definition.id, published_by="publisher-1")

    await repo.upsert_draft(definition.id, {"nodes": ["work-in-progress"]}, created_by="designer-2")

    await repo.rollback_to(definition.id, target_version_no=1, published_by="publisher-2")

    draft = await repo.get_draft(definition.id)
    assert draft is not None
    assert draft.flow_spec == {"nodes": ["work-in-progress"]}


# ---------------------------------------------------------------------------
# 17.6 — the note records the rollback's origin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_records_note_referencing_source_version(repo, flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    await repo.upsert_draft(definition.id, {"nodes": ["v1"]}, created_by="designer-1")
    await repo.publish_draft(definition.id, published_by="publisher-1")
    await repo.upsert_draft(definition.id, {"nodes": ["v2"]}, created_by="designer-1")
    await repo.publish_draft(definition.id, published_by="publisher-1")

    restored = await repo.rollback_to(
        definition.id, target_version_no=1, published_by="publisher-2"
    )

    assert "1" in restored.notes


# ---------------------------------------------------------------------------
# 17.7 — rolling back to an unknown version is a clear error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_to_unknown_version_raises(repo, flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    with pytest.raises(FlowVersionConflictError):
        await repo.rollback_to(definition.id, target_version_no=99, published_by="publisher-1")


@pytest.mark.asyncio
async def test_rollback_to_a_draft_version_raises(repo, flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    draft = await repo.upsert_draft(definition.id, {"nodes": ["wip"]}, created_by="designer-1")

    with pytest.raises(FlowVersionConflictError):
        await repo.rollback_to(
            definition.id, target_version_no=draft.version_no, published_by="publisher-1"
        )
