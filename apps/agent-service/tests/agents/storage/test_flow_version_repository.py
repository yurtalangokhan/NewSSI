"""Tests for FlowVersionRepository — draft read/write against a real DB.

Uses the SQLite harness from tests/agents/storage/conftest.py (Task 14) so
"only one draft exists after two saves" and "version_no increments past
gaps" are proven against real constraint enforcement, not assumed.

Spec: .tmp/flow-canvas-design.md section 5.2.
Brief: .tmp/flow-canvas-task-15-brief.md
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from core.db.models.agent_definition import AgentDefinitionModel, FlowVersionStatus
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
# 15.1 / 15.2 — upsert_draft creates then updates in place
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_draft_creates_first_draft(repo, flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    draft = await repo.upsert_draft(definition.id, {"nodes": [], "edges": []}, created_by="user-1")

    assert draft.status == FlowVersionStatus.DRAFT.value
    assert draft.created_by == "user-1"
    assert draft.definition_id == definition.id


@pytest.mark.asyncio
async def test_upsert_draft_updates_existing_draft_in_place(repo, flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    first = await repo.upsert_draft(definition.id, {"nodes": [1]}, created_by="user-1")
    second = await repo.upsert_draft(definition.id, {"nodes": [1, 2]}, created_by="user-1")

    assert second.id == first.id
    assert second.flow_spec == {"nodes": [1, 2]}

    versions = await repo.list_versions(definition.id)
    drafts = [v for v in versions if v.status == FlowVersionStatus.DRAFT.value]
    assert len(drafts) == 1


# ---------------------------------------------------------------------------
# 15.3 — get_draft absence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_draft_returns_none_when_no_draft(repo, flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    draft = await repo.get_draft(definition.id)

    assert draft is None


# ---------------------------------------------------------------------------
# 15.4 / 15.5 — next_version_no
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_next_version_no_starts_at_one(repo, flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    next_no = await repo.next_version_no(definition.id)

    assert next_no == 1


@pytest.mark.asyncio
async def test_next_version_no_increments_past_highest(repo, flow_version_session_factory):
    from core.db.models.agent_definition import AgentFlowVersionModel

    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)
        session.add(
            AgentFlowVersionModel(
                definition_id=definition.id,
                version_no=5,
                flow_spec={},
                status=FlowVersionStatus.ARCHIVED.value,
            )
        )
        await session.commit()

    next_no = await repo.next_version_no(definition.id)

    assert next_no == 6


@pytest.mark.asyncio
async def test_next_version_no_ignores_an_existing_drafts_tentative_number(
    repo, flow_version_session_factory
):
    """A draft's own version_no is a tentative placeholder (assigned at
    creation, per upsert_draft's docstring) — it must not count toward "the
    next number" when something (Task 16's publish) asks for it again.
    Otherwise the first publish of a brand-new flow would skip straight to
    version 2: the draft itself (version_no=1, no other rows exist) would be
    counted as if it were an existing published version."""
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    await repo.upsert_draft(definition.id, {"nodes": []}, created_by="u1")

    next_no = await repo.next_version_no(definition.id)

    assert next_no == 1


# ---------------------------------------------------------------------------
# 15.6 — list_versions ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_versions_orders_newest_first(repo, flow_version_session_factory):
    from core.db.models.agent_definition import AgentFlowVersionModel

    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)
        session.add_all(
            [
                AgentFlowVersionModel(
                    definition_id=definition.id,
                    version_no=1,
                    flow_spec={},
                    status=FlowVersionStatus.ARCHIVED.value,
                ),
                AgentFlowVersionModel(
                    definition_id=definition.id,
                    version_no=2,
                    flow_spec={},
                    status=FlowVersionStatus.PUBLISHED.value,
                ),
            ]
        )
        await session.commit()

    versions = await repo.list_versions(definition.id)

    assert [v.version_no for v in versions] == [2, 1]


# ---------------------------------------------------------------------------
# 15.7 — get_published / get_by_version_no
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_published_returns_the_published_row(repo, flow_version_session_factory):
    from core.db.models.agent_definition import AgentFlowVersionModel

    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)
        session.add(
            AgentFlowVersionModel(
                definition_id=definition.id,
                version_no=1,
                flow_spec={"marker": "published"},
                status=FlowVersionStatus.PUBLISHED.value,
            )
        )
        await session.commit()

    published = await repo.get_published(definition.id)

    assert published is not None
    assert published.flow_spec == {"marker": "published"}


@pytest.mark.asyncio
async def test_get_by_version_no_returns_none_for_unknown_version(
    repo, flow_version_session_factory
):
    async with flow_version_session_factory() as session:
        definition = await _make_definition(session)

    result = await repo.get_by_version_no(definition.id, 99)

    assert result is None
