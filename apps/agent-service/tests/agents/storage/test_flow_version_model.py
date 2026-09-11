"""Tests for AgentFlowVersionModel — the version-history table P3 versioning
is built on. Model tests are schema-declaration checks (always run, no DB);
constraint tests use a real SQLite engine (tests/agents/storage/conftest.py)
so "duplicate version_no raises" and "delete cascades" are proven, not
assumed.

Spec: .tmp/flow-canvas-design.md section 5.1.
Brief: .tmp/flow-canvas-task-14-brief.md
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from core.db.models.agent_definition import (
    AgentDefinitionModel,
    AgentFlowVersionModel,
    FlowVersionStatus,
)


def _make_definition(**overrides) -> AgentDefinitionModel:
    defaults = {"name": f"agent-{uuid4()}", "graph_schema": "flow"}
    defaults.update(overrides)
    return AgentDefinitionModel(**defaults)


def _make_version(
    definition_id, version_no=1, status="draft", **overrides
) -> AgentFlowVersionModel:
    defaults = {
        "definition_id": definition_id,
        "version_no": version_no,
        "flow_spec": {"nodes": [], "edges": []},
        "status": status,
    }
    defaults.update(overrides)
    return AgentFlowVersionModel(**defaults)


# ---------------------------------------------------------------------------
# 14.1 — schema declaration (no DB needed)
# ---------------------------------------------------------------------------


def test_flow_version_model_has_required_columns():
    columns = AgentFlowVersionModel.__table__.columns

    assert not columns["id"].nullable
    assert columns["id"].primary_key
    assert not columns["definition_id"].nullable
    assert not columns["version_no"].nullable
    assert not columns["flow_spec"].nullable
    assert not columns["status"].nullable
    assert columns["created_by"].nullable
    assert columns["published_by"].nullable
    assert not columns["created_at"].nullable
    assert columns["published_at"].nullable
    assert columns["notes"].nullable


def test_flow_version_model_definition_id_is_foreign_key_with_cascade():
    fk = next(iter(AgentFlowVersionModel.__table__.columns["definition_id"].foreign_keys))
    assert fk.column.table.name == "agent_definitions"
    assert fk.ondelete == "CASCADE"


def test_flow_version_model_has_unique_version_no_per_definition_constraint():
    from sqlalchemy import UniqueConstraint

    constraints = [
        c for c in AgentFlowVersionModel.__table__.constraints if isinstance(c, UniqueConstraint)
    ]
    column_sets = [{col.name for col in c.columns} for c in constraints]
    assert {"definition_id", "version_no"} in column_sets


def test_flow_version_model_has_one_draft_per_definition_partial_index():
    indexes = AgentFlowVersionModel.__table__.indexes
    draft_index = next((ix for ix in indexes if ix.unique and "draft" in ix.name), None)
    assert draft_index is not None, "expected a unique partial index enforcing one draft"
    assert {col.name for col in draft_index.columns} == {"definition_id"}


# ---------------------------------------------------------------------------
# 14.2 — status enum
# ---------------------------------------------------------------------------


def test_flow_version_status_enum_values():
    assert {s.value for s in FlowVersionStatus} == {"draft", "published", "archived"}


# ---------------------------------------------------------------------------
# 14.3 — version_no unique per definition (real DB behavior)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_version_no_unique_per_definition(flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = _make_definition()
        session.add(definition)
        await session.flush()

        session.add(_make_version(definition.id, version_no=1, status="published"))
        await session.flush()

        session.add(_make_version(definition.id, version_no=1, status="archived"))
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.asyncio
async def test_version_no_can_repeat_across_different_definitions(flow_version_session_factory):
    async with flow_version_session_factory() as session:
        def_a = _make_definition()
        def_b = _make_definition()
        session.add_all([def_a, def_b])
        await session.flush()

        session.add(_make_version(def_a.id, version_no=1, status="published"))
        session.add(_make_version(def_b.id, version_no=1, status="published"))
        await session.flush()  # must not raise


# ---------------------------------------------------------------------------
# 14.4 — one draft per definition (real DB behavior)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_one_draft_per_definition(flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = _make_definition()
        session.add(definition)
        await session.flush()

        session.add(_make_version(definition.id, version_no=1, status="draft"))
        await session.flush()

        session.add(_make_version(definition.id, version_no=2, status="draft"))
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.asyncio
async def test_second_published_version_is_allowed(flow_version_session_factory):
    async with flow_version_session_factory() as session:
        definition = _make_definition()
        session.add(definition)
        await session.flush()

        session.add(_make_version(definition.id, version_no=1, status="published"))
        await session.flush()

        session.add(_make_version(definition.id, version_no=2, status="published"))
        await session.flush()  # must not raise — only "draft" is capped at one


# ---------------------------------------------------------------------------
# 14.5 — agent_definitions gains published_flow_version_id
# ---------------------------------------------------------------------------


def test_definition_gains_published_flow_version_id_column():
    column = AgentDefinitionModel.__table__.columns["published_flow_version_id"]
    assert column.nullable
    fk = next(iter(column.foreign_keys))
    assert fk.column.table.name == "agent_flow_versions"


# ---------------------------------------------------------------------------
# 14.6 — cascade delete (real DB behavior)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deleting_definition_cascades_versions(flow_version_session_factory):
    from sqlalchemy import select

    async with flow_version_session_factory() as session:
        definition = _make_definition()
        session.add(definition)
        await session.flush()

        version = _make_version(definition.id, version_no=1, status="draft")
        session.add(version)
        await session.flush()

        await session.delete(definition)
        await session.commit()

        remaining = await session.execute(
            select(AgentFlowVersionModel).where(
                AgentFlowVersionModel.definition_id == definition.id
            )
        )
        assert remaining.scalar_one_or_none() is None
